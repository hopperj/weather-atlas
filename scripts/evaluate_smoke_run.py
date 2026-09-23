#!/usr/bin/env python3
"""Evaluate a smoke run against a frozen external-observation pair set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_evaluation import evaluate, write_evaluation_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "kind",
        choices=(
            "gfas_inventory",
            "misr_plume_height",
            "naps_pm25",
            "tropomi_aerosol_mid_height",
            "airnow_pm25",
            "aqs_pm25",
        ),
    )
    parser.add_argument("pairs", type=Path)
    parser.add_argument("--run-manifest", type=Path)
    parser.add_argument("--thresholds", type=Path, default=Path("config/smoke/validation.yaml"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.kind,
        args.pairs,
        args.thresholds,
        run_manifest=args.run_manifest,
    )
    if args.output:
        write_evaluation_report(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
