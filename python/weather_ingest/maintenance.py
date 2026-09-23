"""Bounded, dry-run-first catalogue and local-storage maintenance."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from weather_common.db import SqlFileLoader

DEFAULT_MAINTENANCE_LIMIT = 100
MAX_MAINTENANCE_LIMIT = 1000
DEFAULT_TEMPORARY_AGE_HOURS = 48


class MaintenanceError(RuntimeError):
    pass


class UnsafeMaintenancePath(MaintenanceError):
    pass


@dataclass(frozen=True, slots=True)
class MaintenanceOptions:
    execute: bool
    limit: int
    minimum_age_hours: int | None = None
    verify_checksums: bool = False
    fail_on_issue: bool = False


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    object_kind: str
    object_id: int
    relative_path: str
    file_size_bytes: int | None
    sha256: str | None
    status: str


class MaintenanceRepository(Protocol):
    def list_asset_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]: ...

    def list_source_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]: ...

    def mark_pending(self, candidate: RetentionCandidate) -> dict[str, Any] | None: ...

    def mark_deleted(self, candidate: RetentionCandidate) -> dict[str, Any] | None: ...

    def list_registered_local_files(self, *, limit: int) -> list[dict[str, Any]]: ...

    def get_latest_visible_product_run(
        self, product_code: str
    ) -> dict[str, Any] | None: ...

    def list_superseded_product_files(
        self, product_code: str, keep_product_run_id: int, *, limit: int
    ) -> list[dict[str, Any]]: ...

    def expire_superseded_product_runs(
        self, product_code: str, keep_product_run_id: int
    ) -> dict[str, Any] | None: ...


class PostgresMaintenanceRepository:
    """Synchronous repository whose statements all live in reviewed SQL files."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        loader: SqlFileLoader | None = None,
    ) -> None:
        self.database_url = database_url or os.environ["WEATHER_DATABASE_URL"]
        self.loader = loader or SqlFileLoader()

    def _fetch_all(
        self, query_name: str, parameters: Mapping[str, object]
    ) -> list[dict[str, Any]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            return list(connection.execute(self.loader.load(query_name), parameters).fetchall())

    def _fetch_one(
        self, query_name: str, parameters: Mapping[str, object]
    ) -> dict[str, Any] | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            return connection.execute(self.loader.load(query_name), parameters).fetchone()

    def list_asset_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            "maintenance/list_asset_retention_candidates.sql",
            {"as_of": as_of, "limit": limit},
        )

    def list_source_retention_candidates(
        self, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            "maintenance/list_source_retention_candidates.sql",
            {"as_of": as_of, "limit": limit},
        )

    def mark_pending(self, candidate: RetentionCandidate) -> dict[str, Any] | None:
        if candidate.object_kind == "asset":
            return self._fetch_one(
                "maintenance/mark_asset_pending_deletion.sql",
                {"asset_id": candidate.object_id},
            )
        if candidate.object_kind == "source":
            return self._fetch_one(
                "maintenance/mark_source_pending_deletion.sql",
                {"source_object_id": candidate.object_id},
            )
        raise MaintenanceError(f"unsupported retention object kind: {candidate.object_kind}")

    def mark_deleted(self, candidate: RetentionCandidate) -> dict[str, Any] | None:
        if candidate.object_kind == "asset":
            return self._fetch_one(
                "maintenance/mark_asset_deleted.sql", {"asset_id": candidate.object_id}
            )
        if candidate.object_kind == "source":
            return self._fetch_one(
                "maintenance/mark_source_deleted.sql",
                {"source_object_id": candidate.object_id},
            )
        raise MaintenanceError(f"unsupported retention object kind: {candidate.object_kind}")

    def list_registered_local_files(self, *, limit: int) -> list[dict[str, Any]]:
        return self._fetch_all(
            "maintenance/list_registered_local_files.sql", {"limit": limit}
        )

    def get_latest_visible_product_run(
        self, product_code: str
    ) -> dict[str, Any] | None:
        return self._fetch_one(
            "maintenance/get_latest_visible_product_run.sql",
            {"product_code": product_code},
        )

    def list_superseded_product_files(
        self, product_code: str, keep_product_run_id: int, *, limit: int
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            "maintenance/list_superseded_product_files.sql",
            {
                "product_code": product_code,
                "keep_product_run_id": keep_product_run_id,
                "limit": limit,
            },
        )

    def expire_superseded_product_runs(
        self, product_code: str, keep_product_run_id: int
    ) -> dict[str, Any] | None:
        return self._fetch_one(
            "maintenance/expire_superseded_product_runs.sql",
            {
                "product_code": product_code,
                "keep_product_run_id": keep_product_run_id,
            },
        )


def parse_maintenance_options(
    value: object,
    *,
    operation: str,
) -> MaintenanceOptions:
    """Strictly parse one Airflow DAG run configuration."""

    if value is None:
        config: dict[str, object] = {}
    elif isinstance(value, dict):
        config = value
    else:
        raise ValueError("maintenance DAG configuration must be a JSON object")

    common = {"limit"}
    if operation == "retention":
        allowed = common | {"execute"}
    elif operation == "integrity":
        allowed = common | {"verify_checksums", "fail_on_issue"}
    elif operation == "temporary_cleanup":
        allowed = common | {"execute", "minimum_age_hours"}
    else:
        raise ValueError(f"unknown maintenance operation: {operation}")
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unknown maintenance options: {sorted(unknown)}")

    limit = config.get("limit", DEFAULT_MAINTENANCE_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if not 1 <= limit <= MAX_MAINTENANCE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_MAINTENANCE_LIMIT}")

    execute = config.get("execute", False)
    if not isinstance(execute, bool):
        raise ValueError("execute must be a JSON boolean")
    verify_checksums = config.get("verify_checksums", False)
    if not isinstance(verify_checksums, bool):
        raise ValueError("verify_checksums must be a JSON boolean")
    fail_on_issue = config.get("fail_on_issue", False)
    if not isinstance(fail_on_issue, bool):
        raise ValueError("fail_on_issue must be a JSON boolean")

    minimum_age: int | None = None
    if operation == "temporary_cleanup":
        minimum_age = config.get("minimum_age_hours", DEFAULT_TEMPORARY_AGE_HOURS)
        if isinstance(minimum_age, bool) or not isinstance(minimum_age, int):
            raise ValueError("minimum_age_hours must be an integer")
        if not 1 <= minimum_age <= 24 * 365:
            raise ValueError("minimum_age_hours must be between 1 and 8760")

    return MaintenanceOptions(
        execute=execute,
        limit=limit,
        minimum_age_hours=minimum_age,
        verify_checksums=verify_checksums,
        fail_on_issue=fail_on_issue,
    )


def _allowed_roots(object_kind: str) -> frozenset[str]:
    if object_kind == "asset":
        return frozenset({"processed", "derived"})
    if object_kind == "source":
        return frozenset({"raw"})
    if object_kind == "temporary":
        return frozenset({"staging", "temporary"})
    raise UnsafeMaintenancePath(f"unsupported storage object kind: {object_kind}")


def safe_maintenance_path(
    data_root: Path | str,
    relative_path: Path | str,
    *,
    object_kind: str,
) -> Path:
    """Resolve a database path without following or deleting through symlinks."""

    root = Path(data_root).expanduser().resolve(strict=True)
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise UnsafeMaintenancePath(f"unsafe relative storage path: {relative}")
    if relative.parts[0] not in _allowed_roots(object_kind):
        raise UnsafeMaintenancePath(
            f"{object_kind} path is outside its allowed storage class: {relative}"
        )

    candidate = root.joinpath(relative)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise UnsafeMaintenancePath(f"storage path escapes data root: {relative}")

    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise UnsafeMaintenancePath(f"storage path contains a symlink: {relative}")
        if not current.exists():
            break
    return candidate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_descriptor(file_descriptor: int) -> str:
    digest = hashlib.sha256()
    while chunk := os.read(file_descriptor, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _preflight_registered_file(
    path: Path,
    *,
    expected_size: int | None,
    expected_sha256: str | None,
    verify_checksum: bool,
) -> bool:
    """Return False for an already absent file; reject unexpected replacements."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise UnsafeMaintenancePath(f"maintenance target is not a regular file: {path}")
    if expected_size is not None and metadata.st_size != expected_size:
        raise MaintenanceError(
            f"registered size {expected_size} does not match file size "
            f"{metadata.st_size}: {path}"
        )
    if verify_checksum:
        if expected_sha256 is None:
            raise MaintenanceError(f"registered checksum is missing: {path}")
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise MaintenanceError(f"registered checksum does not match file: {path}")
    return True


def _unlink_with_verified_descriptors(
    data_root: Path | str,
    relative_path: Path | str,
    *,
    object_kind: str,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    verify_checksum: bool = False,
    oldest_allowed_mtime: float | None = None,
) -> bool:
    """Unlink one regular file without following path-component symlinks."""

    candidate = safe_maintenance_path(
        data_root, relative_path, object_kind=object_kind
    )
    root = Path(data_root).expanduser().resolve(strict=True)
    relative = candidate.relative_to(root)
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    directory_flags = os.O_RDONLY | os.O_DIRECTORY
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_descriptors.append(os.open(root, directory_flags))
        for part in relative.parts[:-1]:
            try:
                next_descriptor = os.open(
                    part,
                    directory_flags | no_follow,
                    dir_fd=directory_descriptors[-1],
                )
            except FileNotFoundError:
                return False
            directory_descriptors.append(next_descriptor)
        filename = relative.parts[-1]
        try:
            file_descriptor = os.open(
                filename,
                os.O_RDONLY | no_follow,
                dir_fd=directory_descriptors[-1],
            )
        except FileNotFoundError:
            return False
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeMaintenancePath(
                f"maintenance target is not a regular file: {relative}"
            )
        if expected_size is not None and metadata.st_size != expected_size:
            raise MaintenanceError(
                f"registered size {expected_size} does not match file size "
                f"{metadata.st_size}: {relative}"
            )
        if oldest_allowed_mtime is not None and metadata.st_mtime > oldest_allowed_mtime:
            raise MaintenanceError(f"maintenance target is no longer old: {relative}")
        if verify_checksum:
            if expected_sha256 is None:
                raise MaintenanceError(f"registered checksum is missing: {relative}")
            if _sha256_descriptor(file_descriptor) != expected_sha256:
                raise MaintenanceError(
                    f"registered checksum does not match file: {relative}"
                )

        current = os.stat(
            filename, dir_fd=directory_descriptors[-1], follow_symlinks=False
        )
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise MaintenanceError(f"maintenance target changed during verification: {relative}")
        os.unlink(filename, dir_fd=directory_descriptors[-1])
        try:
            os.stat(filename, dir_fd=directory_descriptors[-1], follow_symlinks=False)
        except FileNotFoundError:
            return True
        raise MaintenanceError(f"file still exists after unlink: {relative}")
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


def _candidate(row: Mapping[str, Any], object_kind: str) -> RetentionCandidate:
    return RetentionCandidate(
        object_kind=object_kind,
        object_id=int(row["id"]),
        relative_path=str(row["relative_path"]),
        file_size_bytes=(
            int(row["file_size_bytes"]) if row["file_size_bytes"] is not None else None
        ),
        sha256=str(row["sha256"]) if row["sha256"] is not None else None,
        status=str(row["status"]),
    )


def run_asset_retention(
    repository: MaintenanceRepository,
    data_root: Path | str,
    *,
    execute: bool = False,
    limit: int = DEFAULT_MAINTENANCE_LIMIT,
    as_of: datetime | None = None,
) -> dict[str, object]:
    """Plan or perform at most ``limit`` two-phase catalogue deletions."""

    if not 1 <= limit <= MAX_MAINTENANCE_LIMIT:
        raise ValueError("retention limit is outside the supported range")
    effective_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    asset_rows = repository.list_asset_retention_candidates(
        as_of=effective_time, limit=limit
    )
    candidates = [_candidate(row, "asset") for row in asset_rows]
    remaining = limit - len(candidates)
    if remaining:
        source_rows = repository.list_source_retention_candidates(
            as_of=effective_time, limit=remaining
        )
        candidates.extend(_candidate(row, "source") for row in source_rows)

    deleted = 0
    absent = 0
    failures: list[dict[str, object]] = []
    planned: list[dict[str, object]] = []
    for candidate in candidates:
        try:
            path = safe_maintenance_path(
                data_root, candidate.relative_path, object_kind=candidate.object_kind
            )
            exists = _preflight_registered_file(
                path,
                expected_size=candidate.file_size_bytes,
                expected_sha256=candidate.sha256,
                verify_checksum=execute,
            )
            planned.append(
                {
                    "object_kind": candidate.object_kind,
                    "object_id": candidate.object_id,
                    "relative_path": candidate.relative_path,
                    "file_exists": exists,
                }
            )
            if not execute:
                continue

            pending = repository.mark_pending(candidate)
            if pending is None:
                raise MaintenanceError("candidate state changed before pending transition")
            if str(pending["relative_path"]) != candidate.relative_path:
                raise MaintenanceError("candidate path changed before pending transition")

            # Repeat containment and identity checks through O_NOFOLLOW
            # descriptors after the database transition, then unlink relative
            # to that verified parent directory.
            removed = _unlink_with_verified_descriptors(
                data_root,
                candidate.relative_path,
                object_kind=candidate.object_kind,
                expected_size=candidate.file_size_bytes,
                expected_sha256=candidate.sha256,
                verify_checksum=True,
            )
            if removed:
                deleted += 1
            else:
                absent += 1
            _unlink_with_verified_descriptors(
                data_root,
                candidate.relative_path + ".aux.xml",
                object_kind=candidate.object_kind,
            )
            completed = repository.mark_deleted(candidate)
            if completed is None:
                raise MaintenanceError("pending candidate could not transition to deleted")
        except (MaintenanceError, OSError, ValueError) as error:
            failures.append(
                {
                    "object_kind": candidate.object_kind,
                    "object_id": candidate.object_id,
                    "error": str(error),
                }
            )

    return {
        "mode": "execute" if execute else "dry_run",
        "limit": limit,
        "candidate_count": len(candidates),
        "deleted_file_count": deleted,
        "already_absent_count": absent,
        "failure_count": len(failures),
        "candidates": planned,
        "failures": failures,
    }


def prune_superseded_product_data(
    repository: MaintenanceRepository,
    data_root: Path | str,
    product_code: str,
    *,
    batch_limit: int = MAX_MAINTENANCE_LIMIT,
) -> dict[str, object]:
    """Keep the latest visible run and remove registered files from older runs."""

    if not 1 <= batch_limit <= MAX_MAINTENANCE_LIMIT:
        raise ValueError("latest-run retention limit is outside the supported range")
    keep_run = repository.get_latest_visible_product_run(product_code)
    if keep_run is None:
        return {
            "product_code": product_code,
            "status": "no_visible_run",
            "deleted_file_count": 0,
            "already_absent_count": 0,
            "expired_run_count": 0,
        }

    keep_run_id = int(keep_run["id"])
    deleted = 0
    absent = 0
    failures: list[dict[str, object]] = []
    while True:
        rows = repository.list_superseded_product_files(
            product_code,
            keep_run_id,
            limit=batch_limit,
        )
        if not rows:
            break
        for row in rows:
            candidate = _candidate(row, str(row["object_kind"]))
            try:
                pending = repository.mark_pending(candidate)
                if pending is None:
                    raise MaintenanceError(
                        "superseded object state changed before pending transition"
                    )
                removed = _unlink_with_verified_descriptors(
                    data_root,
                    candidate.relative_path,
                    object_kind=candidate.object_kind,
                    expected_size=candidate.file_size_bytes,
                    expected_sha256=candidate.sha256,
                    verify_checksum=False,
                )
                if removed:
                    deleted += 1
                else:
                    absent += 1
                sidecar = candidate.relative_path + ".aux.xml"
                _unlink_with_verified_descriptors(
                    data_root,
                    sidecar,
                    object_kind=candidate.object_kind,
                )
                if repository.mark_deleted(candidate) is None:
                    raise MaintenanceError(
                        "superseded object could not transition to deleted"
                    )
            except (MaintenanceError, OSError, ValueError) as error:
                failures.append(
                    {
                        "object_kind": candidate.object_kind,
                        "object_id": candidate.object_id,
                        "error": str(error),
                    }
                )
        if failures or len(rows) < batch_limit:
            break

    if failures:
        raise MaintenanceError(
            f"latest-run retention failed for {product_code}: {failures[:3]}"
        )
    expired = repository.expire_superseded_product_runs(product_code, keep_run_id)
    return {
        "product_code": product_code,
        "status": "complete",
        "kept_product_run_id": keep_run_id,
        "kept_run_time": keep_run["run_time"],
        "deleted_file_count": deleted,
        "already_absent_count": absent,
        "expired_run_count": int(expired["expired_count"]) if expired else 0,
    }


def run_integrity_audit(
    repository: MaintenanceRepository,
    data_root: Path | str,
    *,
    limit: int = DEFAULT_MAINTENANCE_LIMIT,
    verify_checksums: bool = False,
) -> dict[str, object]:
    """Compare a bounded set of registered files to local storage without writes."""

    if not 1 <= limit <= MAX_MAINTENANCE_LIMIT:
        raise ValueError("integrity limit is outside the supported range")
    rows = repository.list_registered_local_files(limit=limit)
    issues: list[dict[str, object]] = []
    checked = 0
    total_registered = int(rows[0]["total_registered"]) if rows else 0
    for row in rows:
        checked += 1
        object_kind = str(row["object_kind"])
        try:
            path = safe_maintenance_path(
                data_root, str(row["relative_path"]), object_kind=object_kind
            )
            exists = _preflight_registered_file(
                path,
                expected_size=(
                    int(row["file_size_bytes"])
                    if row["file_size_bytes"] is not None
                    else None
                ),
                expected_sha256=str(row["sha256"]) if row["sha256"] else None,
                verify_checksum=verify_checksums,
            )
            if not exists:
                raise MaintenanceError("registered file is missing")
        except (MaintenanceError, OSError, ValueError) as error:
            issues.append(
                {
                    "object_kind": object_kind,
                    "object_id": int(row["object_id"]),
                    "relative_path": str(row["relative_path"]),
                    "error": str(error),
                }
            )
    return {
        "mode": "read_only",
        "limit": limit,
        "checked_count": checked,
        "total_registered": total_registered,
        "truncated": total_registered > checked,
        "verify_checksums": verify_checksums,
        "issue_count": len(issues),
        "issues": issues,
    }


def _temporary_candidates(
    data_root: Path | str,
    *,
    minimum_age_hours: int,
    limit: int,
    as_of: datetime,
) -> tuple[list[Path], list[str]]:
    root = Path(data_root).expanduser().resolve(strict=True)
    cutoff = as_of.timestamp() - timedelta(hours=minimum_age_hours).total_seconds()
    candidates: list[Path] = []
    skipped_symlinks: list[str] = []
    for storage_class in ("staging", "temporary"):
        class_root = root / storage_class
        if not class_root.exists():
            continue
        if class_root.is_symlink():
            skipped_symlinks.append(storage_class)
            continue
        for directory, directories, filenames in os.walk(class_root, followlinks=False):
            directory_path = Path(directory)
            safe_directories: list[str] = []
            for name in sorted(directories):
                child = directory_path / name
                if child.is_symlink():
                    skipped_symlinks.append(child.relative_to(root).as_posix())
                else:
                    safe_directories.append(name)
            directories[:] = safe_directories
            for filename in sorted(filenames):
                if Path(filename).suffix not in {".part", ".tmp"}:
                    continue
                relative = (directory_path / filename).relative_to(root)
                try:
                    path = safe_maintenance_path(
                        root, relative, object_kind="temporary"
                    )
                    metadata = path.lstat()
                except UnsafeMaintenancePath:
                    skipped_symlinks.append(relative.as_posix())
                    continue
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(metadata.st_mode):
                    skipped_symlinks.append(relative.as_posix())
                    continue
                if stat.S_ISREG(metadata.st_mode) and metadata.st_mtime <= cutoff:
                    candidates.append(path)
                    if len(candidates) >= limit:
                        return candidates, skipped_symlinks
    return candidates, skipped_symlinks


def run_temporary_cleanup(
    data_root: Path | str,
    *,
    execute: bool = False,
    limit: int = DEFAULT_MAINTENANCE_LIMIT,
    minimum_age_hours: int = DEFAULT_TEMPORARY_AGE_HOURS,
    as_of: datetime | None = None,
) -> dict[str, object]:
    """Plan or remove only old .part/.tmp regular files in temporary classes."""

    if not 1 <= limit <= MAX_MAINTENANCE_LIMIT:
        raise ValueError("cleanup limit is outside the supported range")
    if minimum_age_hours < 1:
        raise ValueError("minimum_age_hours must be positive")
    effective_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    paths, skipped_symlinks = _temporary_candidates(
        data_root,
        minimum_age_hours=minimum_age_hours,
        limit=limit,
        as_of=effective_time,
    )
    root = Path(data_root).expanduser().resolve(strict=True)
    failures: list[dict[str, str]] = []
    deleted = 0
    for candidate in paths:
        relative = candidate.relative_to(root)
        if not execute:
            continue
        try:
            removed = _unlink_with_verified_descriptors(
                root,
                relative,
                object_kind="temporary",
                oldest_allowed_mtime=(
                    effective_time.timestamp()
                    - timedelta(hours=minimum_age_hours).total_seconds()
                ),
            )
            if removed:
                deleted += 1
        except (MaintenanceError, OSError, ValueError) as error:
            failures.append({"relative_path": relative.as_posix(), "error": str(error)})
    return {
        "mode": "execute" if execute else "dry_run",
        "limit": limit,
        "minimum_age_hours": minimum_age_hours,
        "candidate_count": len(paths),
        "deleted_file_count": deleted,
        "skipped_symlink_count": len(skipped_symlinks),
        "candidates": [path.relative_to(root).as_posix() for path in paths],
        "skipped_symlinks": skipped_symlinks,
        "failure_count": len(failures),
        "failures": failures,
    }
