from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from weather_ingest.maintenance import (
    RetentionCandidate,
    UnsafeMaintenancePath,
    parse_maintenance_options,
    prune_superseded_product_data,
    run_asset_retention,
    run_integrity_audit,
    run_temporary_cleanup,
    safe_maintenance_path,
)


class FakeRepository:
    def __init__(
        self,
        *,
        assets: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
        registered: list[dict[str, Any]] | None = None,
    ) -> None:
        self.assets = assets or []
        self.sources = sources or []
        self.registered = registered or []
        self.events: list[tuple[str, str, int]] = []
        self.source_limit: int | None = None
        self.latest_visible: dict[str, Any] | None = None
        self.expired_count = 0

    def list_asset_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]:
        del as_of
        return self.assets[:limit]

    def list_source_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]:
        del as_of
        self.source_limit = limit
        return self.sources[:limit]

    def mark_pending(self, candidate: RetentionCandidate) -> dict[str, Any]:
        self.events.append(("pending", candidate.object_kind, candidate.object_id))
        return {
            "id": candidate.object_id,
            "relative_path": candidate.relative_path,
            "status": "pending_deletion",
        }

    def mark_deleted(self, candidate: RetentionCandidate) -> dict[str, Any]:
        self.events.append(("deleted", candidate.object_kind, candidate.object_id))
        return {
            "id": candidate.object_id,
            "relative_path": candidate.relative_path,
            "status": "deleted",
        }

    def list_registered_local_files(self, *, limit: int) -> list[dict[str, Any]]:
        return self.registered[:limit]

    def get_latest_visible_product_run(
        self, product_code: str
    ) -> dict[str, Any] | None:
        del product_code
        return self.latest_visible

    def list_superseded_product_files(
        self, product_code: str, keep_product_run_id: int, *, limit: int
    ) -> list[dict[str, Any]]:
        del product_code, keep_product_run_id
        rows = [
            {"object_kind": "asset", **row} for row in self.assets
        ] + [{"object_kind": "source", **row} for row in self.sources]
        pending_ids = {
            (kind, object_id)
            for action, kind, object_id in self.events
            if action == "deleted"
        }
        return [
            row
            for row in rows
            if (str(row["object_kind"]), int(row["id"])) not in pending_ids
        ][:limit]

    def expire_superseded_product_runs(
        self, product_code: str, keep_product_run_id: int
    ) -> dict[str, Any]:
        del product_code, keep_product_run_id
        return {"expired_count": self.expired_count}


def _retention_row(
    object_id: int, relative_path: str, payload: bytes, *, status: str = "available"
) -> dict[str, object]:
    return {
        "id": object_id,
        "relative_path": relative_path,
        "file_size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "status": status,
    }


def test_maintenance_options_are_dry_run_and_bounded_by_default() -> None:
    options = parse_maintenance_options({}, operation="retention")

    assert options.execute is False
    assert options.limit == 100
    with pytest.raises(ValueError, match="JSON boolean"):
        parse_maintenance_options({"execute": "true"}, operation="retention")
    with pytest.raises(ValueError, match="between 1 and 1000"):
        parse_maintenance_options({"limit": 1001}, operation="integrity")
    with pytest.raises(ValueError, match="unknown maintenance options"):
        parse_maintenance_options({"execute": True}, operation="integrity")


def test_safe_path_rejects_wrong_storage_class_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "processed").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "processed" / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeMaintenancePath, match="allowed storage class"):
        safe_maintenance_path(tmp_path, "raw/object.grib2", object_kind="asset")
    with pytest.raises(UnsafeMaintenancePath, match="symlink"):
        safe_maintenance_path(
            tmp_path, "processed/link/object.tif", object_kind="asset"
        )


def test_retention_is_dry_run_until_explicitly_executed(tmp_path: Path) -> None:
    target = tmp_path / "processed" / "eccc" / "asset.tif"
    target.parent.mkdir(parents=True)
    payload = b"registered-cog"
    target.write_bytes(payload)
    repository = FakeRepository(
        assets=[_retention_row(7, "processed/eccc/asset.tif", payload)]
    )

    result = run_asset_retention(repository, tmp_path)

    assert result["mode"] == "dry_run"
    assert target.read_bytes() == payload
    assert repository.events == []


def test_retention_transitions_pending_unlinks_then_marks_deleted(tmp_path: Path) -> None:
    target = tmp_path / "processed" / "eccc" / "asset.tif"
    target.parent.mkdir(parents=True)
    payload = b"registered-cog"
    target.write_bytes(payload)
    repository = FakeRepository(
        assets=[_retention_row(7, "processed/eccc/asset.tif", payload)]
    )

    result = run_asset_retention(repository, tmp_path, execute=True)

    assert result["failure_count"] == 0
    assert result["deleted_file_count"] == 1
    assert not target.exists()
    assert repository.events == [("pending", "asset", 7), ("deleted", "asset", 7)]


def test_retention_reconciles_pending_row_when_file_is_already_absent(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(
        assets=[
            _retention_row(
                9,
                "processed/already-gone.tif",
                b"previous contents",
                status="pending_deletion",
            )
        ]
    )

    result = run_asset_retention(repository, tmp_path, execute=True)

    assert result["already_absent_count"] == 1
    assert result["failure_count"] == 0
    assert repository.events == [("pending", "asset", 9), ("deleted", "asset", 9)]


def test_retention_refuses_replaced_file_before_database_transition(tmp_path: Path) -> None:
    target = tmp_path / "processed" / "asset.tif"
    target.parent.mkdir()
    target.write_bytes(b"0123456789")
    repository = FakeRepository(
        assets=[_retention_row(8, "processed/asset.tif", b"abcdefghij")]
    )

    result = run_asset_retention(repository, tmp_path, execute=True)

    assert result["failure_count"] == 1
    assert target.read_bytes() == b"0123456789"
    assert repository.events == []


def test_retention_total_limit_is_shared_by_assets_and_sources(tmp_path: Path) -> None:
    repository = FakeRepository(
        assets=[
            _retention_row(1, "processed/a.tif", b"a"),
            _retention_row(2, "processed/b.tif", b"b"),
        ],
        sources=[_retention_row(3, "raw/c.grib2", b"c", status="downloaded")],
    )

    result = run_asset_retention(repository, tmp_path, limit=3)

    assert result["candidate_count"] == 3
    assert repository.source_limit == 1


def test_latest_run_retention_removes_older_registered_files(tmp_path: Path) -> None:
    asset = tmp_path / "processed" / "eccc" / "old.tif"
    source = tmp_path / "raw" / "eccc" / "old.grib2"
    asset.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    asset.write_bytes(b"old cog")
    source.write_bytes(b"old grib")
    sidecar = Path(str(asset) + ".aux.xml")
    sidecar.write_bytes(b"aux")
    source_sidecar = Path(str(source) + ".aux.xml")
    source_sidecar.write_bytes(b"raw aux")
    repository = FakeRepository(
        assets=[_retention_row(1, "processed/eccc/old.tif", b"old cog")],
        sources=[
            _retention_row(
                2,
                "raw/eccc/old.grib2",
                b"old grib",
                status="downloaded",
            )
        ],
    )
    repository.latest_visible = {
        "id": 10,
        "run_time": datetime(2026, 7, 19, tzinfo=UTC),
    }
    repository.expired_count = 3

    result = prune_superseded_product_data(repository, tmp_path, "hrdps")

    assert result["deleted_file_count"] == 2
    assert result["expired_run_count"] == 3
    assert not asset.exists()
    assert not sidecar.exists()
    assert not source.exists()
    assert not source_sidecar.exists()


def test_integrity_audit_reports_missing_and_size_mismatch(tmp_path: Path) -> None:
    existing = tmp_path / "raw" / "existing.grib2"
    existing.parent.mkdir()
    existing.write_bytes(b"123")
    repository = FakeRepository(
        registered=[
            {
                "object_kind": "source",
                "object_id": 1,
                "relative_path": "raw/existing.grib2",
                "file_size_bytes": 99,
                "sha256": None,
                "status": "downloaded",
                "total_registered": 3,
            },
            {
                "object_kind": "asset",
                "object_id": 2,
                "relative_path": "processed/missing.tif",
                "file_size_bytes": 10,
                "sha256": "0" * 64,
                "status": "available",
                "total_registered": 3,
            },
        ]
    )

    result = run_integrity_audit(repository, tmp_path, limit=2)

    assert result["issue_count"] == 2
    assert result["truncated"] is True
    assert result["total_registered"] == 3


def test_temporary_cleanup_only_removes_old_regular_partial_files(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    temporary = tmp_path / "temporary"
    raw = tmp_path / "raw"
    staging.mkdir()
    temporary.mkdir()
    raw.mkdir()
    old_part = staging / "old.tif.part"
    old_tmp = temporary / "old.tmp"
    recent_part = staging / "recent.part"
    other = staging / "keep.tif"
    wrong_class = raw / "old.part"
    for path in (old_part, old_tmp, recent_part, other, wrong_class):
        path.write_bytes(b"fixture")
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    old_timestamp = (now - timedelta(hours=72)).timestamp()
    recent_timestamp = (now - timedelta(hours=1)).timestamp()
    for path in (old_part, old_tmp, other, wrong_class):
        os.utime(path, (old_timestamp, old_timestamp))
    os.utime(recent_part, (recent_timestamp, recent_timestamp))

    dry_run = run_temporary_cleanup(
        tmp_path, minimum_age_hours=48, as_of=now
    )
    executed = run_temporary_cleanup(
        tmp_path, execute=True, minimum_age_hours=48, as_of=now
    )

    assert dry_run["candidate_count"] == 2
    assert executed["deleted_file_count"] == 2
    assert not old_part.exists()
    assert not old_tmp.exists()
    assert recent_part.exists()
    assert other.exists()
    assert wrong_class.exists()


def test_temporary_cleanup_does_not_follow_symlink_directories(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    outside = tmp_path / "outside"
    staging.mkdir()
    outside.mkdir()
    outside_partial = outside / "old.part"
    outside_partial.write_bytes(b"must remain")
    (staging / "linked").symlink_to(outside, target_is_directory=True)

    result = run_temporary_cleanup(
        tmp_path,
        execute=True,
        minimum_age_hours=1,
        as_of=datetime(2026, 7, 16, 12, tzinfo=UTC),
    )

    assert result["candidate_count"] == 0
    assert result["skipped_symlink_count"] == 1
    assert outside_partial.exists()
