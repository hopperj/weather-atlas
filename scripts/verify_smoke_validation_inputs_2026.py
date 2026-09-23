#!/usr/bin/env python3
"""Audit the frozen 2026 smoke-validation input collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_HOTSPOT_GAPS = frozenset(date(2026, 3, 25) + timedelta(days=offset) for offset in range(6))
EXPECTED_CFFDRS_GAPS = frozenset({date(2026, 5, 10)})


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"manifest is not a JSON object: {path}")
    return payload


def _verify_artifact(
    root: Path,
    record: dict[str, Any],
    *,
    manifest_directory: Path | None = None,
    full_hash: bool,
) -> int:
    relative = record.get("relative_path")
    if isinstance(relative, str):
        path = root / relative
    elif manifest_directory is not None and isinstance(record.get("filename"), str):
        path = manifest_directory / record["filename"]
    else:
        raise ValueError("artifact record has no resolvable path")
    expected_size = record.get("size_bytes")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size <= 0:
        raise ValueError(f"artifact has an invalid size: {path}")
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        raise ValueError(f"artifact is missing or has the wrong size: {path}")
    expected_hash = record.get("sha256")
    if not isinstance(expected_hash, str) or SHA256_PATTERN.fullmatch(expected_hash) is None:
        raise ValueError(f"artifact has no valid SHA-256: {path}")
    if full_hash and _sha256(path) != expected_hash:
        raise ValueError(f"artifact SHA-256 mismatch: {path}")
    return expected_size


def verify_gfs(
    root: Path,
    start: date,
    end: date,
    *,
    full_hash: bool,
) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    for day in _dates(start, end):
        directory = (
            root
            / "raw"
            / "noaa"
            / "gfs"
            / "global_1p00"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%d}"
            / "00"
        )
        manifest = _load_json(directory / "manifest.json")
        if manifest.get("forecast_hours") != list(range(0, 25, 3)):
            raise ValueError(f"GFS forecast-hour coverage is wrong for {day}")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != 9:
            raise ValueError(f"GFS file count is wrong for {day}")
        for record in files:
            total_bytes += _verify_artifact(
                root,
                record,
                manifest_directory=directory,
                full_hash=full_hash,
            )
            file_count += 1
    return {
        "status": "complete",
        "cycle_count": len(_dates(start, end)),
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def verify_cffdrs(
    root: Path,
    start: date,
    end: date,
    *,
    full_hash: bool,
) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    gaps = []
    for day in _dates(start, end):
        path = (
            root
            / "raw"
            / "nrcan"
            / "cwfis"
            / "cffdrs"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%d}"
            / "manifest.json"
        )
        if not path.is_file():
            gaps.append(day)
            continue
        manifest = _load_json(path)
        grids = manifest.get("grids")
        if not isinstance(grids, dict) or set(grids) != {"ffmc", "dmc", "dc"}:
            raise ValueError(f"CFFDRS field coverage is wrong for {day}")
        for record in grids.values():
            total_bytes += _verify_artifact(root, record, full_hash=full_hash)
            file_count += 1
    if set(gaps) != set(EXPECTED_CFFDRS_GAPS):
        raise ValueError(f"unexpected CFFDRS gaps: {[value.isoformat() for value in gaps]}")
    return {
        "status": "complete_with_provider_gap",
        "date_count": len(_dates(start, end)) - len(gaps),
        "file_count": file_count,
        "total_bytes": total_bytes,
        "provider_gaps": [value.isoformat() for value in gaps],
    }


def verify_hotspots(
    root: Path,
    start: date,
    end: date,
    *,
    full_hash: bool,
) -> dict[str, Any]:
    total_bytes = 0
    feature_count = 0
    gaps = []
    completed = 0
    for day in _dates(start, end):
        path = (
            root
            / "processed"
            / "nrcan"
            / "cwfis"
            / "firem3"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%d}"
            / "manifest.json"
        )
        if not path.is_file():
            gaps.append(day)
            continue
        manifest = _load_json(path)
        total_bytes += _verify_artifact(root, manifest["raw"], full_hash=full_hash)
        total_bytes += _verify_artifact(root, manifest["geojson"], full_hash=full_hash)
        feature_count += int(manifest["feature_count"])
        completed += 1
    if set(gaps) != set(EXPECTED_HOTSPOT_GAPS):
        raise ValueError(f"unexpected CWFIS hotspot gaps: {[value.isoformat() for value in gaps]}")
    return {
        "status": "complete_with_provider_gaps",
        "date_count": completed,
        "feature_count": feature_count,
        "total_raw_and_processed_bytes": total_bytes,
        "provider_gaps": [value.isoformat() for value in gaps],
    }


def verify_record_manifest(
    root: Path,
    manifest_path: Path,
    *,
    expected_count: int,
    full_hash: bool,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != expected_count:
        raise ValueError(f"file count is wrong in {manifest_path}")
    total_bytes = sum(_verify_artifact(root, record, full_hash=full_hash) for record in records)
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        "file_count": len(records),
        "total_bytes": total_bytes,
    }


def verify_gfas(
    root: Path,
    start: date,
    end: date,
    *,
    full_hash: bool,
) -> dict[str, Any]:
    manifest_path = (
        root
        / "derived"
        / "smoke"
        / "validation"
        / "input-archives"
        / f"gfas-v1.4.2-{start}_{end}"
        / "manifest.json"
    )
    manifest = _load_json(manifest_path)
    expected_days = len(_dates(start, end))
    files = manifest.get("files")
    provider_manifests = manifest.get("provider_manifests")
    if not isinstance(files, list) or len(files) != expected_days * 220:
        raise ValueError("GFAS selected-file coverage is incomplete")
    if not isinstance(provider_manifests, list) or len(provider_manifests) != expected_days * 25:
        raise ValueError("GFAS provider-manifest coverage is incomplete")
    total_bytes = sum(
        _verify_artifact(root, record, full_hash=full_hash)
        for record in [*files, *provider_manifests]
    )
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        "data_file_count": len(files),
        "provider_manifest_count": len(provider_manifests),
        "total_bytes_including_provider_manifests": total_bytes,
    }


def verify_catalogues(
    root: Path,
    start: date,
    end: date,
    *,
    full_hash: bool,
) -> dict[str, Any]:
    manifest_path = (
        root
        / "raw"
        / "catalogues"
        / "smoke_validation_2026"
        / f"{start}_{end}-manifest.json"
    )
    manifest = _load_json(manifest_path)
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != 5:
        raise ValueError("satellite catalogue manifest has the wrong record count")
    artifact_count = 0
    total_bytes = 0
    for record in records:
        candidates = []
        if isinstance(record.get("catalogue"), dict):
            candidates.append(record["catalogue"])
        if isinstance(record.get("catalogues"), list):
            candidates.extend(record["catalogues"])
        for artifact in candidates:
            total_bytes += _verify_artifact(root, artifact, full_hash=full_hash)
            artifact_count += 1
    if artifact_count != 7:
        raise ValueError("satellite catalogue artifact count is incomplete")
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        "artifact_count": artifact_count,
        "total_bytes": total_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--spinup-days", type=int, default=1)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--full-hash", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve()
    input_start = args.start - timedelta(days=args.spinup_days)
    results = {
        "gfs": verify_gfs(root, input_start, args.end, full_hash=args.full_hash),
        "cffdrs": verify_cffdrs(root, input_start, args.end, full_hash=args.full_hash),
        "hotspots": verify_hotspots(root, input_start, args.end, full_hash=args.full_hash),
        "airnow": verify_record_manifest(
            root,
            root
            / "raw"
            / "epa"
            / "airnow"
            / "hourly_observations"
            / f"{input_start}_{args.end}-manifest.json",
            expected_count=len(_dates(input_start, args.end)) * 24,
            full_hash=args.full_hash,
        ),
        "aqs": verify_record_manifest(
            root,
            root / "raw" / "epa" / "aqs" / "2026" / "manifest.json",
            expected_count=3,
            full_hash=args.full_hash,
        ),
        "gfas": verify_gfas(root, args.start, args.end, full_hash=args.full_hash),
        "tropomi": verify_record_manifest(
            root,
            root
            / "raw"
            / "copernicus"
            / "sentinel-5p"
            / "tropomi"
            / "offl"
            / "l2_aer_lh"
            / f"{args.start}_{args.end}-manifest.json",
            expected_count=977,
            full_hash=args.full_hash,
        ),
        "mcd64a1": verify_record_manifest(
            root,
            root / "raw" / "nasa" / "lpdaac" / "mcd64a1" / "v061" / "2026-manifest.json",
            expected_count=69,
            full_hash=args.full_hash,
        ),
        "catalogues": verify_catalogues(
            root,
            args.start,
            args.end,
            full_hash=args.full_hash,
        ),
        "optional_authorization_gaps": {
            "status": "optional",
            "earthcare_atlid": {
                "catalogued_atl_fm_2a": 1408,
                "catalogued_atl_ebd_2a": 1408,
                "data_status": "requires ESA EO Sign-In authorization",
            },
        },
    }
    payload = {
        "schema_version": 1,
        "status": "complete_with_provider_gaps_and_optional_authorization_gap",
        "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "full_hash_verification": args.full_hash,
        "experiment_start": args.start.isoformat(),
        "experiment_end": args.end.isoformat(),
        "input_start": input_start.isoformat(),
        "results": results,
    }
    output = args.output or (
        root
        / "derived"
        / "smoke"
        / "validation"
        / "input-archives"
        / f"observations-2026-{args.start}_{args.end}"
        / "verification.json"
    )
    _atomic_json(output, payload)
    print(
        json.dumps(
            {"status": payload["status"], "output": str(output), "results": results}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
