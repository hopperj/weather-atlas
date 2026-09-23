#!/usr/bin/env python3
"""Build frozen-event daily burned areas from QA-screened MCD64A1 pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from weather_ingest.mcd64a1 import build_mcd64a1_event_areas


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcd64-root", type=Path, required=True)
    parser.add_argument("--cmr", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/smoke/mcd64a1_area.yaml"),
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()

    report = build_mcd64a1_event_areas(
        mcd64_root=args.mcd64_root,
        cmr_path=args.cmr,
        events_path=args.events,
        config_path=args.config,
        start=args.start,
        end=args.end,
    )
    report_path = args.output_directory / "mcd64a1-event-areas.json"
    _atomic_json(report_path, report)
    summary_path = args.output_directory / "mcd64a1-area-summary.json"
    _atomic_json(
        summary_path,
        {
            "schema_version": 1,
            "operator_version": report["operator_version"],
            "created_at": report["created_at"],
            "experiment_interval": report["experiment_interval"],
            "configuration": report["configuration"],
            "sources": report["sources"],
            "summary": report["summary"],
            "event_areas_path": report_path.as_posix(),
            "event_areas_sha256": _sha256(report_path),
        },
    )
    print(
        json.dumps(
            {
                **report["summary"],
                "event_areas_path": report_path.as_posix(),
                "event_areas_sha256": _sha256(report_path),
                "summary_path": summary_path.as_posix(),
                "summary_sha256": _sha256(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["summary"]["independent_daily_burned_area_available"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
