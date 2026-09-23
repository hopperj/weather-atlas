#!/usr/bin/env python3
"""Build the performance-blind portion of the W4 NAPS background-exclusion ledger."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import zipfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

RADIUS_KM = 150.0
POST_DETECTION_HOURS = 24


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def haversine_km(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    first_latitude_rad, second_latitude_rad = map(
        math.radians, (first_latitude, second_latitude)
    )
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    value = (
        math.sin(latitude_delta / 2.0) ** 2
        + math.cos(first_latitude_rad)
        * math.cos(second_latitude_rad)
        * math.sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * 6371.0088 * math.asin(math.sqrt(value))


def ceil_hour(value: datetime) -> datetime:
    result = value.replace(minute=0, second=0, microsecond=0)
    return result if result == value else result + timedelta(hours=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--surface-ledger", type=Path, required=True)
    parser.add_argument("--hotspots", type=Path, required=True)
    parser.add_argument("--hotspot-manifest", type=Path, required=True)
    parser.add_argument("--station-history", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_path = args.source_ledger.expanduser().resolve()
    surface_path = args.surface_ledger.expanduser().resolve()
    hotspot_path = args.hotspots.expanduser().resolve()
    hotspot_manifest_path = args.hotspot_manifest.expanduser().resolve()
    station_history_path = args.station_history.expanduser().resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    surface = json.loads(surface_path.read_text(encoding="utf-8"))
    hotspot_manifest = json.loads(
        hotspot_manifest_path.read_text(encoding="utf-8")
    )
    station_history = json.loads(
        station_history_path.read_text(encoding="utf-8")
    )
    if hotspot_manifest["file"]["sha256"] != sha256(hotspot_path):
        raise ValueError("Fire M3 archive does not match its acquisition manifest")
    if station_history["status"] != "constant_coordinates_in_final_archive":
        raise ValueError("station coordinate history has not passed its frozen check")

    source_dates = sorted(
        set(source["required_acquisition_dates_retained_and_reserve"])
    )
    source_date_values = {
        datetime.fromisoformat(value).date() for value in source_dates
    }
    start = min(source_date_values) - timedelta(days=14)
    end = max(source_date_values) + timedelta(days=14)
    stations = [
        {
            "station_id": str(item["station_id"]),
            "latitude": float(item["latitude"]),
            "longitude": float(item["longitude"]),
        }
        for item in surface["stations"]
    ]
    station_index: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for station in stations:
        latitude = station["latitude"]
        longitude = station["longitude"]
        for row in range(math.floor(latitude) - 2, math.floor(latitude) + 3):
            longitude_margin = max(
                2,
                math.ceil(
                    RADIUS_KM
                    / max(1.0, 111.0 * math.cos(math.radians(latitude)))
                ),
            )
            for column in range(
                math.floor(longitude) - longitude_margin,
                math.floor(longitude) + longitude_margin + 1,
            ):
                station_index[(row, column)].append(station)

    excluded: dict[tuple[str, datetime], dict[str, Any]] = {}
    scanned = 0
    period_canadian_rows = 0
    proximity_matches = 0
    with zipfile.ZipFile(hotspot_path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError("expected exactly one Fire M3 CSV member")
        with archive.open(members[0]) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            )
            required = {"rep_date", "country", "lat", "lon", "sensor", "source"}
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Fire M3 CSV lacks fields: {sorted(missing)}")
            for row in reader:
                scanned += 1
                if row["country"].strip().upper() != "C":
                    continue
                observed = datetime.strptime(
                    row["rep_date"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=UTC)
                if not start <= observed.date() <= end:
                    continue
                period_canadian_rows += 1
                latitude = float(row["lat"])
                longitude = float(row["lon"])
                candidates = station_index.get(
                    (math.floor(latitude), math.floor(longitude)),
                    [],
                )
                for station in candidates:
                    distance = haversine_km(
                        latitude,
                        longitude,
                        station["latitude"],
                        station["longitude"],
                    )
                    if distance > RADIUS_KM:
                        continue
                    proximity_matches += 1
                    first_hour = ceil_hour(observed)
                    for offset in range(POST_DETECTION_HOURS + 1):
                        interval_end = first_hour + timedelta(hours=offset)
                        key = station["station_id"], interval_end
                        existing = excluded.get(key)
                        candidate = {
                            "station_id": station["station_id"],
                            "interval_end_utc": interval_end.isoformat(),
                            "reason": "satellite_active_fire_within_frozen_radius",
                            "nearest_detection_distance_km": distance,
                            "supporting_detection_at_utc": observed.isoformat(),
                            "sensor": row["sensor"].strip(),
                            "source": row["source"].strip(),
                        }
                        if (
                            existing is None
                            or distance < existing["nearest_detection_distance_km"]
                        ):
                            excluded[key] = candidate

    payload = {
        "schema_version": 1,
        "artifact_type": "w4-background-exclusion-ledger",
        "status": "machine_fire_screen_complete_pending_independent_review",
        "concentration_used_for_exclusion": False,
        "candidate_output_used_for_exclusion": False,
        "excluded_dates": source_dates,
        "excluded_station_hours": [
            excluded[key] for key in sorted(excluded)
        ],
        "frozen_other_fire_rule": {
            "source": "NRCan CWFIS Fire M3 annual hotspot archive",
            "maximum_station_distance_km": RADIUS_KM,
            "excluded_interval": (
                "hour ending at the first whole UTC hour at/after detection "
                f"through {POST_DETECTION_HOURS} hours afterward, inclusive"
            ),
            "national_candidate_source_dates_excluded_separately": True,
        },
        "required_review_categories": {
            "candidate_source_dates": "complete_machine_rule",
            "other_satellite_detected_fire_or_smoke_influence": "complete_machine_rule",
            "known_non_wildfire_exceptional_events": "pending_independent_external_record_review",
            "maintenance_or_calibration": (
                "final NAPS missing/invalid values rejected; pending independent metadata review"
            ),
            "unstable_station_metadata": "complete_constant_coordinate_archive_check",
        },
        "independent_review": {
            "reviewer": None,
            "reviewed_at": None,
            "decision": "pending",
            "comments": [],
        },
        "period": {
            "background_screen_start": start.isoformat(),
            "background_screen_end": end.isoformat(),
        },
        "counts": {
            "candidate_source_date_count": len(source_dates),
            "station_count": len(stations),
            "annual_hotspot_rows_scanned": scanned,
            "period_canadian_hotspot_rows": period_canadian_rows,
            "station_detection_proximity_matches": proximity_matches,
            "excluded_station_hour_count": len(excluded),
        },
        "sources": {
            "source_ledger": artifact(source_path),
            "surface_ledger": artifact(surface_path),
            "hotspots": artifact(hotspot_path),
            "hotspot_manifest": artifact(hotspot_manifest_path),
            "station_history": artifact(station_history_path),
        },
        "limitations": [
            "The fixed active-fire radius is an input-only smoke-contamination screen, not a dispersion model.",
            "An independent air-quality reviewer must check exceptional-event and maintenance records before this ledger can be marked reviewed.",
        ],
    }
    atomic_json(args.output.expanduser().resolve(), payload)
    print(
        json.dumps(
            {
                "output": args.output.expanduser().resolve().as_posix(),
                "sha256": sha256(args.output.expanduser().resolve()),
                "status": payload["status"],
                **payload["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
