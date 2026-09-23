#!/usr/bin/env python3
"""Run the frozen standalone November CFFEPS/FLEXPART validation candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_validation_candidate import run_validation_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--event-areas", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument(
        "--candidate-config",
        type=Path,
        default=Path("config/smoke/validation_candidate.yaml"),
    )
    parser.add_argument(
        "--fuel-crosswalk",
        type=Path,
        default=Path("config/smoke/fuel_crosswalk.yaml"),
    )
    parser.add_argument(
        "--emission-factors",
        type=Path,
        default=Path("config/smoke/emission_factors.yaml"),
    )
    parser.add_argument(
        "--cffeps-executable",
        type=Path,
        default=Path("cffeps/bin/weatherapp-cffeps"),
    )
    parser.add_argument("--flexpart-root", type=Path, default=Path("flexpart"))
    parser.add_argument(
        "--flexpart-executable",
        type=Path,
        default=Path("flexpart/src/FLEXPART"),
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--skip-transport", action="store_true")
    parser.add_argument(
        "--transport-workers",
        type=int,
        default=1,
        help="Independent FLEXPART members to execute concurrently (1-8)",
    )
    args = parser.parse_args()

    result = run_validation_candidate(
        data_root=args.data_root,
        event_area_path=args.event_areas,
        events_path=args.events,
        candidate_config_path=args.candidate_config,
        crosswalk_path=args.fuel_crosswalk,
        emission_factors_path=args.emission_factors,
        cffeps_executable=args.cffeps_executable,
        flexpart_root=args.flexpart_root,
        flexpart_executable=args.flexpart_executable,
        output_directory=args.output_directory,
        run_transport=not args.skip_transport,
        transport_workers=args.transport_workers,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "wall_time_seconds": result["wall_time_seconds"],
                "mass_kg_by_species": result["mass_kg_by_species"],
                "transport_day_count": len(result["transport_days"]),
                "manifest_path": result["manifest_path"],
                "manifest_sha256": result["manifest_sha256"],
                "emissions_path": result["emissions_path"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
