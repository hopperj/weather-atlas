#!/usr/bin/env python3
"""Build immutable MISR/FLEXPART fire-overpass height pairs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from weather_ingest.vertical_plume_observations import (
    VerticalPlumeObservation,
    sample_flexpart_vertical,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation-ledger", type=Path, required=True)
    parser.add_argument(
        "--model-map",
        type=Path,
        required=True,
        help="JSON mapping observation_id to immutable FLEXPART NetCDF path",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    ledger = json.loads(arguments.observation_ledger.read_text())
    model_map = json.loads(arguments.model_map.read_text())
    rows = []
    rejections = []
    model_sources = []
    for payload in ledger["observations"]:
        observation = VerticalPlumeObservation(
            **{
                **payload,
                "polygon": tuple(tuple(point) for point in payload["polygon"]),
            }
        )
        model_text = model_map.get(observation.observation_id)
        if model_text is None:
            rejections.append(
                {
                    "observation_id": observation.observation_id,
                    "reason": "missing_model_mapping",
                }
            )
            continue
        model_path = Path(model_text)
        try:
            sampled = sample_flexpart_vertical(model_path, observation)
        except ValueError as exc:
            rejections.append(
                {
                    "observation_id": observation.observation_id,
                    "reason": "model_operator_rejection",
                    "detail": str(exc),
                }
            )
            continue
        rows.append(
            {
                "observed": observation.primary_height_agl_m,
                "modelled": sampled["modelled_mean_height_agl_m"],
                "observed_upper_agl_m": observation.upper_height_agl_m,
                "modelled_95pct_top_agl_m": sampled["modelled_95pct_top_agl_m"],
                "observation_id": observation.observation_id,
                "event_id": observation.event_id,
                "overpass_id": observation.overpass_id,
                "observed_at_utc": observation.observed_at_utc,
                "valid_retrieval_points": observation.valid_retrieval_points,
                "column_weight_ng_m2": sampled["column_weight_ng_m2"],
            }
        )
        model_sources.append(
            {
                "path": model_path.as_posix(),
                "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            }
        )
    arguments.output_directory.mkdir(parents=True, exist_ok=True)
    pairs_path = arguments.output_directory / "misr-pairs.csv"
    temporary = pairs_path.with_name(pairs_path.name + ".part")
    with temporary.open("w", newline="", encoding="utf-8") as destination:
        fields = list(rows[0]) if rows else ["observed", "modelled"]
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, pairs_path)
    rejection_path = arguments.output_directory / "rejection-ledger.json"
    rejection_path.write_text(json.dumps({"rejections": rejections}, indent=2) + "\n")
    manifest = {
        "schema_version": 1,
        "artifact_type": "misr-flexpart-height-pairs",
        "operator_version": "misr-flexpart-polygon-linear-v1",
        "pair_count": len(rows),
        "rejection_count": len(rejections),
        "pairs_path": pairs_path.as_posix(),
        "pairs_sha256": hashlib.sha256(pairs_path.read_bytes()).hexdigest(),
        "observation_ledger_sha256": hashlib.sha256(
            arguments.observation_ledger.read_bytes()
        ).hexdigest(),
        "model_sources": model_sources,
    }
    (arguments.output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
