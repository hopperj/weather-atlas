#!/usr/bin/env python3
"""Freeze W4 final-NAPS station/method metadata before model pairing."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from weather_ingest.naps_pm25 import read_naps_pm25
from weather_ingest.smoke_phase0 import atomic_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--naps", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    observations, manifest = read_naps_pm25(arguments.naps)
    by_station = defaultdict(list)
    for item in observations:
        by_station[item.station_id].append(item)
    station_metadata = {
        "schema_version": 1,
        "artifact_type": "final-naps-primary-station-metadata",
        "selection_rule": (
            "method with most valid final hours per station; "
            "lexicographically smallest method code breaks ties"
        ),
        "performance_values_used_for_method_selection": False,
        "stations": [
            {
                "station_id": station_id,
                "method_code": values[0].method_code,
                "city": values[0].city,
                "province": values[0].province,
                "latitude": values[0].latitude,
                "longitude": values[0].longitude,
                "valid_hour_count": len(values),
            }
            for station_id, values in sorted(by_station.items())
        ],
    }
    station_history = {
        "schema_version": 1,
        "artifact_type": "final-naps-station-coordinate-history",
        "coordinate_change_policy": "reject until an explicit dated station history is frozen",
        "stations_with_coordinate_changes": [],
        "station_count": len(by_station),
        "status": "constant_coordinates_in_final_archive",
    }
    exclusion_template = {
        "schema_version": 1,
        "artifact_type": "w4-background-exclusion-ledger",
        "status": "pending_independent_fire_smoke_and_exceptional_event_review",
        "concentration_used_for_exclusion": False,
        "excluded_dates": [],
        "excluded_station_hours": [],
        "required_review_categories": [
            "candidate source dates",
            "other satellite-detected fire or smoke influence",
            "known non-wildfire exceptional events",
            "maintenance or calibration",
            "unstable station metadata",
        ],
    }
    arguments.output_directory.mkdir(parents=True, exist_ok=True)
    atomic_json(arguments.output_directory / "raw-manifest.json", manifest)
    atomic_json(
        arguments.output_directory / "station-metadata.json",
        station_metadata,
    )
    atomic_json(
        arguments.output_directory / "station-history.json",
        station_history,
    )
    atomic_json(
        arguments.output_directory / "background-exclusion-ledger.template.json",
        exclusion_template,
    )
    print(
        json.dumps(
            {
                "station_count": len(by_station),
                "observation_count": len(observations),
                "output_directory": arguments.output_directory.as_posix(),
            }
        )
    )


if __name__ == "__main__":
    main()
