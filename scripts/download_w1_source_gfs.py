#!/usr/bin/env python3
"""Download and freeze historical GFS cycles required by a W1 source ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from download_smoke_validation_inputs import download_gfs
from weather_ingest.gfs_profiles import resolve_complete_cycle
from weather_ingest.noaa_gfs import GfsIngestionSettings, cycle_relative_directory


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
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


def consecutive_spans(days: list[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    spans: list[tuple[date, date]] = []
    start = previous = days[0]
    for day in days[1:]:
        if day != previous + timedelta(days=1):
            spans.append((start, previous))
            start = day
        previous = day
    spans.append((start, previous))
    return spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spinup-days", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.spinup_days < 0 or not 1 <= args.workers <= 8:
        parser.error("invalid spin-up or worker count")

    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    source_dates = {
        date.fromisoformat(value)
        for value in ledger["required_acquisition_dates_retained_and_reserve"]
    }
    cycle_dates = sorted(
        {
            source_day - timedelta(days=offset)
            for source_day in source_dates
            for offset in range(args.spinup_days + 1)
        }
    )
    root = args.data_root.expanduser().resolve()
    summaries = [
        download_gfs(root, start, end, args.workers)
        for start, end in consecutive_spans(cycle_dates)
    ]

    cycle_records = []
    for day in cycle_dates:
        cycle = datetime.combine(day, time(), tzinfo=UTC)
        manifest = (
            root
            / cycle_relative_directory(GfsIngestionSettings(), cycle)
            / "manifest.json"
        )
        payload, files = resolve_complete_cycle(manifest)
        cycle_records.append(
            {
                "cycle": cycle.isoformat().replace("+00:00", "Z"),
                "manifest_path": manifest.as_posix(),
                "manifest_sha256": sha256(manifest),
                "file_count": len(files),
                "forecast_hours": payload["forecast_hours"],
                "total_bytes": sum(item.stat().st_size for item in files),
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "w1-historical-gfs-acquisition-ledger",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "complete",
        "source_candidate_ledger": {
            "path": args.ledger.resolve().as_posix(),
            "sha256": sha256(args.ledger),
        },
        "policy": {
            "product": "NOAA GFS global_1p00",
            "cycle": "00Z",
            "forecast_hours": list(cycle_records[0]["forecast_hours"]),
            "spinup_days": args.spinup_days,
            "source_date_count": len(source_dates),
            "cycle_date_count": len(cycle_dates),
            "selection": "retained and frozen reserve positive-area source dates",
        },
        "download_summaries": summaries,
        "cycles": cycle_records,
        "total_file_count": sum(item["file_count"] for item in cycle_records),
        "total_bytes": sum(item["total_bytes"] for item in cycle_records),
    }
    atomic_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": args.output.resolve().as_posix(),
                "sha256": sha256(args.output),
                "cycle_count": len(cycle_records),
                "file_count": payload["total_file_count"],
                "total_bytes": payload["total_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
