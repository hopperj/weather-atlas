#!/usr/bin/env python3
"""Build a checked, provenance-preserving GFAS daily-analysis GRIB bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from eccodes import codes_get, codes_grib_new_from_file, codes_release

PARAMETERS = ("pm2p5fire", "cofire", "bcfire")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _inspect_source(path: Path, expected_day: date, expected_name: str) -> dict[str, Any]:
    with path.open("rb") as source:
        handle = codes_grib_new_from_file(source)
        if handle is None:
            raise ValueError(f"empty GRIB source: {path}")
        try:
            metadata = {
                "short_name": str(codes_get(handle, "shortName")),
                "data_date": int(codes_get(handle, "dataDate")),
                "data_time": int(codes_get(handle, "dataTime")),
                "step_range": str(codes_get(handle, "stepRange")),
                "validity_date": int(codes_get(handle, "validityDate")),
                "validity_time": int(codes_get(handle, "validityTime")),
            }
        finally:
            codes_release(handle)
        extra_handle = codes_grib_new_from_file(source)
        if extra_handle is not None:
            codes_release(extra_handle)
            raise ValueError(f"expected one GRIB message in source: {path}")
    if metadata["short_name"] != expected_name:
        raise ValueError(f"unexpected parameter in {path}: {metadata['short_name']}")
    if metadata["data_date"] != int(expected_day.strftime("%Y%m%d")):
        raise ValueError(f"unexpected analysis date in {path}: {metadata['data_date']}")
    if metadata["data_time"] != 0 or metadata["step_range"] != "0-24":
        raise ValueError(f"source is not the 00 UTC 24-hour analysis: {path}")
    return {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        **metadata,
    }


def build_bundle(
    *,
    raw_root: Path,
    output_path: Path,
    dates: list[date],
    command: list[str] | None = None,
) -> dict[str, Any]:
    selected_dates = sorted(set(dates))
    if not selected_dates:
        raise ValueError("at least one date is required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, Any]] = []
    for day in selected_dates:
        directory = raw_root / day.strftime("%Y/%m/%d/00")
        for parameter in PARAMETERS:
            filename = (
                f"z_cams_c_ecmf_{day:%Y%m%d}0000_gfas_an_sfc_024_{parameter}.grib"
            )
            path = directory / filename
            if not path.is_file():
                raise FileNotFoundError(path)
            sources.append(_inspect_source(path, day, parameter))

    temporary = output_path.with_name(output_path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("xb") as destination:
            for source_record in sources:
                with Path(source_record["path"]).open("rb") as source:
                    shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)

    report = {
        "schema_version": 1,
        "product": "cams_gfas_v1_4_2_daily_analysis_validation_bundle",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "command": command if command is not None else sys.argv,
        "dates": [day.isoformat() for day in selected_dates],
        "parameters": list(PARAMETERS),
        "temporal_operator": "00_utc_analysis_accumulation_step_0_24",
        "message_count": len(sources),
        "sources": sources,
        "bundle": {
            "path": output_path.as_posix(),
            "size_bytes": output_path.stat().st_size,
            "sha256": _sha256(output_path),
        },
    }
    manifest_path = output_path.with_name(output_path.name + ".manifest.json")
    _atomic_json(manifest_path, report)
    return report | {
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": _sha256(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", action="append", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    report = build_bundle(
        raw_root=args.raw_root,
        output_path=args.output,
        dates=args.date,
        command=sys.argv,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
