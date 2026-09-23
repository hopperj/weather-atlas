#!/usr/bin/env python3
"""Build the W4 final-NAPS/FLEXPART surface PM2.5 pair table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import date, datetime
from pathlib import Path

from weather_ingest.naps_pm25 import read_naps_pm25
from weather_ingest.surface_pm25_intercomparison import (
    _containing_cell,
    _load_candidate_model,
)
from weather_ingest.surface_smoke_background import calculate_surface_enhancements


def _parse_exclusions(path: Path | None) -> tuple[set[date], set[tuple[str, datetime]]]:
    if path is None:
        return set(), set()
    payload = json.loads(path.read_text())
    dates = {date.fromisoformat(value) for value in payload.get("excluded_dates", [])}
    keys = {
        (item["station_id"], datetime.fromisoformat(item["interval_end_utc"]))
        for item in payload.get("excluded_station_hours", [])
    }
    return dates, keys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--naps", type=Path, required=True)
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--background-exclusions", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--model-threshold", type=float, default=0.01)
    arguments = parser.parse_args()

    observations, naps_manifest = read_naps_pm25(arguments.naps)
    model = _load_candidate_model(arguments.candidate_directory)
    if not math.isclose(
        float(model["surface_layer_upper_m"]),
        50.0,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise ValueError("W4 central operator requires the FLEXPART 0-50 m AGL layer")
    by_station = {}
    target_keys = set()
    model_values = {}
    for observation in observations:
        by_station.setdefault(observation.station_id, observation)
        field = model["model_by_time"].get(observation.interval_end_utc)
        if field is None:
            continue
        row = _containing_cell(model["latitude"], observation.latitude)
        column = _containing_cell(model["longitude"], observation.longitude)
        if row is None or column is None:
            continue
        value = float(field[row, column])
        if math.isfinite(value) and value >= arguments.model_threshold:
            key = (observation.station_id, observation.interval_end_utc)
            target_keys.add(key)
            model_values[key] = value
    source_dates = set(model["source_days"])
    exclusion_dates, exclusion_keys = _parse_exclusions(arguments.background_exclusions)
    exclusion_dates.update(source_dates)
    central, rejections = calculate_surface_enhancements(
        observations,
        target_keys=target_keys,
        excluded_background_dates=exclusion_dates,
        excluded_background_keys=exclusion_keys,
    )
    p20, p20_rejections = calculate_surface_enhancements(
        observations,
        target_keys=target_keys,
        excluded_background_dates=exclusion_dates,
        excluded_background_keys=exclusion_keys,
        statistic="p20",
    )
    arguments.output_directory.mkdir(parents=True, exist_ok=True)

    def write_pairs(name: str, enhancements: list[object]) -> dict[str, object]:
        path = arguments.output_directory / name
        fields = (
            "observed",
            "modelled",
            "station_id",
            "event_id",
            "source_day",
            "interval_end_utc",
            "latitude",
            "longitude",
            "observed_total_pm25_ug_m3",
            "background_pm25_ug_m3",
            "background_sample_count",
            "background_statistic",
        )
        temporary = path.with_name(path.name + ".part")
        with temporary.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            for item in enhancements:
                key = (item.station_id, item.interval_end_utc)
                source_day = model["source_day_by_time"][item.interval_end_utc]
                event_ids = model["event_ids_by_source_day"][source_day]
                writer.writerow(
                    {
                        "observed": item.enhancement_pm25_ug_m3,
                        "modelled": model_values[key],
                        "station_id": item.station_id,
                        "event_id": (
                            "+".join(event_ids)
                            if event_ids
                            else f"unassigned-source-day:{source_day}"
                        ),
                        "source_day": source_day.isoformat(),
                        "interval_end_utc": item.interval_end_utc.isoformat(),
                        "latitude": item.latitude,
                        "longitude": item.longitude,
                        "observed_total_pm25_ug_m3": item.observed_pm25_ug_m3,
                        "background_pm25_ug_m3": item.background_pm25_ug_m3,
                        "background_sample_count": item.background_sample_count,
                        "background_statistic": item.background_statistic,
                    }
                )
        os.replace(temporary, path)
        return {
            "path": path.as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pair_count": len(enhancements),
        }

    central_record = write_pairs("median-background-pairs.csv", central)
    p20_record = write_pairs("p20-background-pairs.csv", p20)
    rejection_path = arguments.output_directory / "rejection-ledger.json"
    rejection_path.write_text(
        json.dumps(
            {"central": rejections, "p20": p20_rejections},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    manifest = {
        "schema_version": 1,
        "artifact_type": "naps-flexpart-surface-pairs",
        "operator_version": "naps-median-background-containing-cell-v1",
        "naps": naps_manifest,
        "central_pairs": central_record,
        "p20_pairs": p20_record,
        "model_sources": model["provenance"],
        "model_threshold_ug_m3": arguments.model_threshold,
        "excluded_background_date_count": len(exclusion_dates),
        "dependence_block": (
            "compound set of source events active on the model source day; "
            "station is the second bootstrap dimension"
        ),
    }
    (arguments.output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
