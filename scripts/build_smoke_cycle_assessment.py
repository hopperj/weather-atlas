#!/usr/bin/env python3
"""Build one W8 cycle assessment or a four-cycle summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_cycle_assessment import (
    assess_cycle_file,
    summarize_counted_cycles,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enqueue-tolerance-minutes", type=float, required=True)
    parser.add_argument("--terminal-sla-hours", type=float, required=True)
    parser.add_argument(
        "--announced-logical-date",
        action="append",
        default=[],
    )
    arguments = parser.parse_args()
    assessments = [
        assess_cycle_file(
            path,
            enqueue_tolerance_minutes=arguments.enqueue_tolerance_minutes,
            terminal_sla_hours=arguments.terminal_sla_hours,
        )
        for path in arguments.cycle_manifest
    ]
    report = (
        summarize_counted_cycles(
            assessments,
            announced_logical_dates=arguments.announced_logical_date,
        )
        if arguments.announced_logical_date
        else assessments[0]
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 2)


if __name__ == "__main__":
    main()
