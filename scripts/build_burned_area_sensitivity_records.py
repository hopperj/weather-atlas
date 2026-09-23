#!/usr/bin/env python3
"""Join MCD64A1, VNP64A1, and CWFIS provider-perimeter area records."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from weather_ingest.burned_area_uncertainty import build_area_sensitivity_records
from weather_ingest.smoke_phase0 import atomic_json


def _provider_areas(path: Path, layer: str) -> dict[int, float]:
    result = subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "/vsistdout/",
            f"/vsizip/{path.resolve()}",
            layer,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    areas = {}
    for feature in payload["features"]:
        properties = feature["properties"]
        uid = int(properties["uid"])
        area = float(properties["area"])
        if uid in areas:
            raise ValueError(f"duplicate CWFIS perimeter UID: {uid}")
        areas[uid] = area
    return areas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--mcd64a1-report", type=Path, required=True)
    parser.add_argument("--vnp64a1-report", type=Path, required=True)
    parser.add_argument("--provider-perimeters", type=Path, required=True)
    parser.add_argument("--provider-layer", default="cc_apt_buf")
    parser.add_argument("--include-reserve", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    payload = build_area_sensitivity_records(
        source_ledger=json.loads(arguments.source_ledger.read_text()),
        mcd64a1_report=json.loads(arguments.mcd64a1_report.read_text()),
        vnp64a1_report=json.loads(arguments.vnp64a1_report.read_text()),
        provider_area_by_uid_ha=_provider_areas(
            arguments.provider_perimeters,
            arguments.provider_layer,
        ),
        include_reserve=arguments.include_reserve,
    )
    payload["sources"] = {
        name: {
            "path": path.resolve().as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for name, path in (
            ("source_ledger", arguments.source_ledger),
            ("mcd64a1_report", arguments.mcd64a1_report),
            ("vnp64a1_report", arguments.vnp64a1_report),
            ("provider_perimeters", arguments.provider_perimeters),
        )
    }
    payload["provider_perimeter_field_contract"] = {
        "uid_field": "uid",
        "area_field": "area",
        "area_units": "hectares",
        "verification": (
            "CWFIS FireM3 archive area agrees with projected geometry area/10000 "
            "for ordinary non-overlap features"
        ),
    }
    atomic_json(arguments.output, payload)
    print(
        json.dumps(
            {
                "record_count": payload["record_count"],
                "output": arguments.output.as_posix(),
            }
        )
    )


if __name__ == "__main__":
    main()
