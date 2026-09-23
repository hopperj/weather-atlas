#!/usr/bin/env python3
"""Build frozen TROPOMI aerosol-height/FLEXPART PM2.5 pair sets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from weather_ingest.tropomi_height_intercomparison import (
    build_tropomi_height_pairs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--tropomi-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--qa-minimum", type=float, default=0.5)
    parser.add_argument("--event-radius-km", type=float, default=50.0)
    parser.add_argument("--maximum-time-offset-minutes", type=float, default=90.0)
    args = parser.parse_args()
    report = build_tropomi_height_pairs(
        candidate_directory=args.candidate_directory,
        tropomi_root=args.tropomi_root,
        output_directory=args.output_directory,
        qa_minimum=args.qa_minimum,
        event_radius_km=args.event_radius_km,
        maximum_time_offset_minutes=args.maximum_time_offset_minutes,
        command=sys.argv,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
