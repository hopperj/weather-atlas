#!/usr/bin/env python3
"""Build frozen species-specific CFFEPS/GFAS grid-cell-day pair sets."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from weather_ingest.gfas_intercomparison import SPECIES_TO_GFAS, build_gfas_pairs


def _bbox(value: str) -> tuple[float, float, float, float]:
    try:
        parts = tuple(float(item) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox values must be numeric") from exc
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox requires west,south,east,north")
    return parts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emissions", type=Path, required=True)
    parser.add_argument(
        "--gfas",
        action="append",
        type=Path,
        required=True,
        help="repeat for each immutable GFAS GRIB batch",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--date",
        action="append",
        type=date.fromisoformat,
        dest="evaluation_dates",
        help="repeat for non-contiguous evaluation dates; defaults to every interval day",
    )
    parser.add_argument("--bbox", type=_bbox, required=True)
    parser.add_argument(
        "--species",
        action="append",
        choices=sorted(SPECIES_TO_GFAS),
        help="repeat to select species; defaults to PM25, CO, and BC",
    )
    parser.add_argument("--numerical-zero-kg", type=float, default=1e-12)
    parser.add_argument("--reference-product", default="gfas-v1.2")
    args = parser.parse_args()
    report = build_gfas_pairs(
        emissions_path=args.emissions,
        gfas_path=args.gfas,
        output_directory=args.output_directory,
        start=args.start,
        end=args.end,
        bbox=args.bbox,
        species=args.species or SPECIES_TO_GFAS,
        evaluation_dates=args.evaluation_dates,
        reference_product=args.reference_product,
        numerical_zero_kg=args.numerical_zero_kg,
        command=sys.argv,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
