#!/usr/bin/env python3
"""Build an input-only historical Fire M3 candidate-event snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from weather_ingest.fbp_fuels import resolve_fbp_fuel
from weather_ingest.fire_events import Detection, EventMatchingConfig, reconcile_events

SELECTION_SEED = "cffeps-flexpart-w1-2023-input-only-perimeter-screen-v1"


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


def hash_rank(uid: int) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}|{uid}".encode()).hexdigest()


def point_in_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > latitude) != (previous[1] > latitude):
            crossing = (previous[0] - current[0]) * (
                latitude - current[1]
            ) / (previous[1] - current[1]) + current[0]
            if longitude < crossing:
                inside = not inside
        previous = current
    return inside


def point_in_geometry(
    longitude: float, latitude: float, geometry: dict[str, Any]
) -> bool:
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    for polygon in polygons:
        if point_in_ring(longitude, latitude, polygon[0]) and not any(
            point_in_ring(longitude, latitude, hole) for hole in polygon[1:]
        ):
            return True
    return False


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    coordinates = [
        point
        for polygon in polygons
        for ring in polygon
        for point in ring
    ]
    return (
        min(point[0] for point in coordinates),
        min(point[1] for point in coordinates),
        max(point[0] for point in coordinates),
        max(point[1] for point in coordinates),
    )


def load_perimeters(path: Path) -> list[dict[str, Any]]:
    process = subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "/vsistdout/",
            f"/vsizip/{path.resolve()}",
            "cc_apt_buf",
            "-t_srs",
            "EPSG:4326",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"perimeter reprojection failed: {process.stderr[-1000:]}")
    features = json.loads(process.stdout).get("features", [])
    result = []
    for feature in features:
        properties = feature["properties"]
        area = float(properties["area"])
        if area < 100:
            stratum = "weak"
            subband = "weak"
        elif area <= 1000:
            stratum = "moderate"
            subband = "moderate"
        else:
            stratum = "major"
            if area <= 10_000:
                subband = "major_1k_10k"
            elif area <= 100_000:
                subband = "major_10k_100k"
            else:
                subband = "major_over_100k"
        geometry = feature["geometry"]
        result.append(
            {
                "uid": int(properties["uid"]),
                "consistent_id": (
                    int(properties["consis_id"])
                    if properties["consis_id"] is not None
                    else None
                ),
                "hotspot_count": int(properties["hcount"]),
                "first_observed_at": properties["firstdate"],
                "last_observed_at": properties["lastdate"],
                "screening_area_ha": area,
                "screening_stratum": stratum,
                "screening_subband": subband,
                "geometry": geometry,
                "bbox": geometry_bbox(geometry),
            }
        )
    return result


def select_perimeters(perimeters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = {
        "weak": 12,
        "moderate": 12,
        "major_1k_10k": 6,
        "major_10k_100k": 6,
        "major_over_100k": 6,
    }
    by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in perimeters:
        by_band[item["screening_subband"]].append(item)
    selected = []
    for band, count in targets.items():
        ranked = sorted(by_band[band], key=lambda item: hash_rank(item["uid"]))
        if len(ranked) < count:
            raise ValueError(f"perimeter band {band} has only {len(ranked)} candidates")
        selected.extend(ranked[:count])
    return sorted(selected, key=lambda item: item["uid"])


def spatial_index(
    perimeters: list[dict[str, Any]],
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    index: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for item in perimeters:
        west, south, east, north = item["bbox"]
        for longitude in range(math.floor(west), math.floor(east) + 1):
            for latitude in range(math.floor(south), math.floor(north) + 1):
                index[(longitude, latitude)].append(item)
    return index


def detection_id(
    observed: datetime, latitude: float, longitude: float, sensor: str
) -> str:
    identity = (
        f"{observed.isoformat().replace('+00:00', 'Z')}|"
        f"{latitude:.5f}|{longitude:.5f}|{sensor}"
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def load_detections(
    hotspot_archive: Path,
    *,
    start: date,
    end: date,
    perimeters: list[dict[str, Any]],
    crosswalk_path: Path,
) -> tuple[list[Detection], dict[str, Any]]:
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk = {
        str(key).upper(): str(value).upper()
        for key, value in crosswalk_payload["rules"].items()
    }
    index = spatial_index(perimeters)
    detections: dict[str, Detection] = {}
    counters: Counter[str] = Counter()
    perimeter_counts: Counter[int] = Counter()
    with zipfile.ZipFile(hotspot_archive) as archive:
        member = f"{start.year}_hotspots.csv"
        with archive.open(member) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            )
            required = {
                "rep_date",
                "sensor",
                "lat",
                "lon",
                "country",
                "agency",
                "ecozone",
                "fuel",
                "ffmc",
                "dmc",
                "dc",
            }
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Fire M3 archive lacks columns: {sorted(missing)}")
            for row in reader:
                counters["rows_scanned"] += 1
                observed = datetime.strptime(
                    row["rep_date"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=UTC)
                if not start <= observed.date() <= end:
                    continue
                counters["rows_in_period"] += 1
                if row["country"].strip().upper() != "C":
                    continue
                counters["canadian_rows"] += 1
                if row["sensor"].strip() != "VIIRS-I":
                    continue
                counters["canadian_viirs_i_rows"] += 1
                latitude = float(row["lat"])
                longitude = float(row["lon"])
                candidates = index.get((math.floor(longitude), math.floor(latitude)), [])
                matches = [
                    item
                    for item in candidates
                    if item["bbox"][0] <= longitude <= item["bbox"][2]
                    and item["bbox"][1] <= latitude <= item["bbox"][3]
                    and point_in_geometry(longitude, latitude, item["geometry"])
                ]
                if not matches:
                    continue
                counters["matched_rows"] += 1
                fuel_text = row["fuel"].strip()
                resolved = resolve_fbp_fuel(fuel_text, crosswalk)
                if resolved is None:
                    counters[f"unsupported_fuel:{fuel_text or 'blank'}"] += 1
                    continue
                identity = detection_id(
                    observed, latitude, longitude, row["sensor"].strip()
                )
                properties = {
                    "detection_id": identity,
                    "observed_at": observed.isoformat().replace("+00:00", "Z"),
                    "source": row.get("source", "").strip(),
                    "sensor": row["sensor"].strip(),
                    "agency": row["agency"].strip(),
                    "ecozone": row["ecozone"].strip(),
                    "fuel": fuel_text,
                    "model_fuel": resolved.model_code,
                    "ffmc": float(row["ffmc"]),
                    "dmc": float(row["dmc"]),
                    "dc": float(row["dc"]),
                    "frp": float(row.get("frp") or 0),
                    "source_perimeter_uids": sorted(item["uid"] for item in matches),
                }
                candidate = Detection(
                    detection_id=identity,
                    observed_at=observed,
                    latitude=latitude,
                    longitude=longitude,
                    fuel=resolved.model_code,
                    properties=properties,
                )
                existing = detections.get(identity)
                if existing is not None and existing != candidate:
                    raise ValueError(f"conflicting duplicate detection: {identity}")
                if existing is not None:
                    counters["exact_duplicate_detection"] += 1
                    continue
                detections[identity] = candidate
                for item in matches:
                    perimeter_counts[item["uid"]] += 1
    return sorted(detections.values(), key=lambda item: item.detection_id), {
        "counts": dict(sorted(counters.items())),
        "selected_perimeter_detection_counts": {
            str(item["uid"]): perimeter_counts[item["uid"]]
            for item in perimeters
        },
        "fuel_crosswalk": {
            "path": crosswalk_path.as_posix(),
            "sha256": sha256(crosswalk_path),
            "version": crosswalk_payload["crosswalk_version"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hotspots", type=Path, required=True)
    parser.add_argument("--perimeters", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--event-config",
        type=Path,
        default=Path("config/smoke/event_matching.yaml"),
    )
    parser.add_argument(
        "--fuel-crosswalk",
        type=Path,
        default=Path("config/smoke/fuel_crosswalk.yaml"),
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.end < arguments.start:
        parser.error("--end precedes --start")

    all_perimeters = load_perimeters(arguments.perimeters)
    selected = select_perimeters(all_perimeters)
    detections, detection_report = load_detections(
        arguments.hotspots,
        start=arguments.start,
        end=arguments.end,
        perimeters=selected,
        crosswalk_path=arguments.fuel_crosswalk,
    )
    config = EventMatchingConfig.from_yaml(arguments.event_config)
    events = reconcile_events(detections, config)
    perimeter_by_uid = {item["uid"]: item for item in selected}
    for event in events["events"]:
        perimeter_uids = sorted(
            {
                uid
                for detection in event["detections"]
                for uid in detection["source_perimeter_uids"]
            }
        )
        screening = [perimeter_by_uid[uid] for uid in perimeter_uids]
        event["input_only_screening"] = {
            "source_perimeter_uids": perimeter_uids,
            "perimeter_area_ha_max": max(
                item["screening_area_ha"] for item in screening
            ),
            "perimeter_strata": sorted(
                {item["screening_stratum"] for item in screening}
            ),
            "ecozones": sorted(
                {
                    detection["ecozone"]
                    for detection in event["detections"]
                    if detection["ecozone"]
                }
            ),
            "agencies": sorted(
                {
                    detection["agency"]
                    for detection in event["detections"]
                    if detection["agency"]
                }
            ),
        }
    output = arguments.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    builder_path = Path(__file__).resolve()
    event_implementation_path = Path(reconcile_events.__code__.co_filename).resolve()
    events_path = output / "candidate-events.json"
    atomic_json(events_path, events)
    report = {
        "schema_version": 1,
        "artifact_type": "w1-input-only-historical-event-candidate-snapshot",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "selection_firewall": {
            "model_output_accessed": False,
            "model_performance_used": False,
            "selection_variables": [
                "Fire M3 buffered-perimeter area band",
                "deterministic seeded hash rank",
                "Fire M3 location, time, fuel, ecozone, and CFFDRS fields",
            ],
        },
        "screening": {
            "seed": SELECTION_SEED,
            "available_perimeter_count": len(all_perimeters),
            "selected_perimeter_count": len(selected),
            "selected_strata": dict(
                sorted(Counter(item["screening_stratum"] for item in selected).items())
            ),
            "selected_subbands": dict(
                sorted(Counter(item["screening_subband"] for item in selected).items())
            ),
            "selected_perimeters": [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"geometry", "bbox"}
                }
                for item in selected
            ],
        },
        "sources": {
            "hotspots": {
                "path": arguments.hotspots.as_posix(),
                "sha256": sha256(arguments.hotspots),
            },
            "perimeters": {
                "path": arguments.perimeters.as_posix(),
                "sha256": sha256(arguments.perimeters),
            },
            "event_config": {
                "path": arguments.event_config.as_posix(),
                "sha256": sha256(arguments.event_config),
            },
            "builder": {
                "path": builder_path.as_posix(),
                "sha256": sha256(builder_path),
            },
            "event_reconciliation_implementation": {
                "path": event_implementation_path.as_posix(),
                "sha256": sha256(event_implementation_path),
            },
        },
        "detections": detection_report,
        "events": {
            "path": events_path.as_posix(),
            "sha256": sha256(events_path),
            "event_count": events["event_count"],
            "detection_count": events["detection_count"],
        },
    }
    report_path = output / "candidate-event-report.json"
    atomic_json(report_path, report)
    print(
        json.dumps(
            {
                "event_count": events["event_count"],
                "detection_count": events["detection_count"],
                "events_path": str(events_path),
                "events_sha256": sha256(events_path),
                "report_path": str(report_path),
                "report_sha256": sha256(report_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
