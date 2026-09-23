#!/usr/bin/env python3
"""Build secondary CALIOP smoke-layer/FLEXPART profile pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np
from weather_ingest.caliop_profiles import read_caliop_layer_csv
from weather_ingest.vertical_plume_observations import (
    VerticalPlumeObservation,
    sample_flexpart_vertical,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layers", type=Path, required=True)
    parser.add_argument("--model-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    model_map = json.loads(arguments.model_map.read_text())
    rows = []
    rejections = []
    for layer in read_caliop_layer_csv(arguments.layers):
        model_text = model_map.get(layer.profile_id)
        if model_text is None:
            rejections.append({"profile_id": layer.profile_id, "reason": "missing_model_mapping"})
            continue
        epsilon = 0.005
        observation = VerticalPlumeObservation(
            observation_id=layer.profile_id,
            event_id=layer.event_id,
            overpass_id=layer.profile_id,
            observed_at_utc=layer.observed_at_utc.isoformat(),
            product="CALIOP aerosol layer",
            product_version="frozen analyst export",
            primary_height_agl_m=layer.midpoint_agl_m,
            upper_height_agl_m=layer.top_agl_m,
            zero_wind_height_agl_m=None,
            valid_retrieval_points=1,
            polygon=(
                (layer.longitude - epsilon, layer.latitude - epsilon),
                (layer.longitude + epsilon, layer.latitude - epsilon),
                (layer.longitude + epsilon, layer.latitude + epsilon),
                (layer.longitude - epsilon, layer.latitude + epsilon),
                (layer.longitude - epsilon, layer.latitude - epsilon),
            ),
            terrain_reference="CALIOP layer base/top converted to local AGL",
            qa_status=layer.qa_status,
            role="secondary",
            source_path=layer.source_path,
            source_sha256=layer.source_sha256,
        )
        try:
            sample = sample_flexpart_vertical(Path(model_text), observation)
        except ValueError as exc:
            rejections.append(
                {
                    "profile_id": layer.profile_id,
                    "reason": "model_operator_rejection",
                    "detail": str(exc),
                }
            )
            continue
        rows.append(
            {
                "profile_id": layer.profile_id,
                "event_id": layer.event_id,
                "observed_midpoint_agl_m": layer.midpoint_agl_m,
                "observed_base_agl_m": layer.base_agl_m,
                "observed_top_agl_m": layer.top_agl_m,
                "modelled_mean_agl_m": sample["modelled_mean_height_agl_m"],
                "modelled_95pct_top_agl_m": sample["modelled_95pct_top_agl_m"],
                "model_column_weight_ng_m2": sample["column_weight_ng_m2"],
            }
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_name(arguments.output.name + ".part")
    with netCDF4.Dataset(temporary, "w") as dataset:
        dataset.createDimension("pair", len(rows))
        dataset.setncattr("artifact_type", "caliop_flexpart_profile_pairs")
        dataset.setncattr("operator_version", "caliop-point-linear-time-v1")
        for name in ("profile_id", "event_id"):
            dataset.createVariable(name, str, ("pair",))[:] = np.asarray(
                [row[name] for row in rows],
                dtype=object,
            )
        for name in (
            "observed_midpoint_agl_m",
            "observed_base_agl_m",
            "observed_top_agl_m",
            "modelled_mean_agl_m",
            "modelled_95pct_top_agl_m",
            "model_column_weight_ng_m2",
        ):
            dataset.createVariable(name, "f8", ("pair",))[:] = [row[name] for row in rows]
    temporary.replace(arguments.output)
    manifest = {
        "schema_version": 1,
        "artifact_type": "caliop-flexpart-profile-pair-manifest",
        "pair_count": len(rows),
        "rejections": rejections,
        "output": arguments.output.as_posix(),
        "output_sha256": hashlib.sha256(arguments.output.read_bytes()).hexdigest(),
        "layers_sha256": hashlib.sha256(arguments.layers.read_bytes()).hexdigest(),
    }
    manifest_path = arguments.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
