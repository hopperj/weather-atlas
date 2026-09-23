#!/usr/bin/env python3
"""Build frozen AirNow or AQS surface-PM2.5/FLEXPART pair sets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from weather_ingest.surface_pm25_intercomparison import build_surface_pm25_pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("network", choices=("airnow", "aqs"))
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--airnow-root", type=Path)
    parser.add_argument("--airnow-manifest", type=Path, action="append")
    parser.add_argument("--aqs-archive", type=Path, action="append")
    parser.add_argument("--aqs-manifest", type=Path)
    parser.add_argument("--background-window-days", type=int, default=14)
    parser.add_argument("--minimum-background-values", type=int, default=7)
    parser.add_argument("--model-minimum-ug-m3", type=float, default=0.01)
    args = parser.parse_args()
    report = build_surface_pm25_pairs(
        network=args.network,
        candidate_directory=args.candidate_directory,
        output_directory=args.output_directory,
        airnow_root=args.airnow_root,
        airnow_manifests=args.airnow_manifest,
        aqs_archives=args.aqs_archive,
        aqs_manifest=args.aqs_manifest,
        background_window_days=args.background_window_days,
        minimum_background_values=args.minimum_background_values,
        model_minimum_ug_m3=args.model_minimum_ug_m3,
        command=sys.argv,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
