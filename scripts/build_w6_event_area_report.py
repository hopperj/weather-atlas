#!/usr/bin/env python3
"""Build a cohort-specific event-area report with independent W6 curves."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from weather_ingest.burned_area_uncertainty import augment_event_area_report
from weather_ingest.smoke_phase0 import atomic_json


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-area-report", type=Path, required=True)
    parser.add_argument("--independent-curves", type=Path, required=True)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    source_ledger = json.loads(arguments.source_ledger.read_text())
    report = augment_event_area_report(
        event_area_report=json.loads(arguments.event_area_report.read_text()),
        independent_curves=json.loads(arguments.independent_curves.read_text()),
        retained_event_ids={
            str(item["event_id"]) for item in source_ledger["retained_events"]
        },
    )
    report["w6_area_sensitivity"]["sources"] = {
        name: {
            "path": path.resolve().as_posix(),
            "sha256": _sha256(path),
        }
        for name, path in (
            ("event_area_report", arguments.event_area_report),
            ("independent_curves", arguments.independent_curves),
            ("source_ledger", arguments.source_ledger),
        )
    }
    atomic_json(arguments.output, report)
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "sha256": _sha256(arguments.output),
                "retained_event_count": report["w6_area_sensitivity"][
                    "retained_event_count"
                ],
                "nontrivial_at_cohort_scale": report["w6_area_sensitivity"][
                    "nontrivial_at_cohort_scale"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
