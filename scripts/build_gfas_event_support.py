#!/usr/bin/env python3
"""Build the frozen input-only W2 GFAS event-support masks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from weather_ingest.gfas_event_support import (
    atomic_json,
    build_support_manifest,
    build_support_records,
    sha256,
    write_sparse_support_netcdf,
)
from weather_ingest.mcd64a1 import build_mcd64a1_event_areas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcd64-root", type=Path, required=True)
    parser.add_argument("--cmr", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    source_ledger = json.loads(args.source_ledger.read_text(encoding="utf-8"))
    support_event_ids = {
        str(event["event_id"])
        for event in [
            *source_ledger["retained_events"],
            *source_ledger["reserve_events"],
        ]
    }
    area_report = build_mcd64a1_event_areas(
        mcd64_root=args.mcd64_root.resolve(),
        cmr_path=args.cmr.resolve(),
        events_path=args.events.resolve(),
        config_path=args.config.resolve(),
        start=args.start,
        end=args.end,
        support_event_ids=support_event_ids,
    )
    support = build_support_records(
        area_report=area_report,
        source_ledger=source_ledger,
    )
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    support_path = output_directory / "event-support-mask.nc"
    output = write_sparse_support_netcdf(support_path, support)
    manifest = build_support_manifest(
        support=support,
        output=output,
        sources={
            "cmr": args.cmr,
            "events": args.events,
            "source_ledger": args.source_ledger,
            "configuration": args.config,
        },
        command=sys.argv,
    )
    manifest_path = output_directory / "event-support-manifest.json"
    atomic_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "exact_record_count": support["exact_record_count"],
                "dilated_record_count": support["dilated_record_count"],
                "output": output,
                "manifest": {
                    "path": manifest_path.as_posix(),
                    "sha256": sha256(manifest_path),
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
