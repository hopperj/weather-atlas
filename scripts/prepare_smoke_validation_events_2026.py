#!/usr/bin/env python3
"""Build the frozen Canadian 2026 Fire M3 event ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from weather_ingest.fbp_fuels import resolve_fbp_fuel
from weather_ingest.fire_events import Detection, EventMatchingConfig, reconcile_events

BOUNDARY_HOST = "naturalearth.s3.amazonaws.com"
BOUNDARY_URL = (
    "https://naturalearth.s3.amazonaws.com/5.1.1/10m_cultural/"
    "ne_10m_admin_0_countries.zip"
)
EXPECTED_HOTSPOT_GAPS = frozenset(
    date(2026, 3, 25) + timedelta(days=offset) for offset in range(6)
)


def _dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date must not precede start date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
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


def _download_boundary(root: Path, url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != BOUNDARY_HOST:
        raise ValueError("Natural Earth boundary URL is outside the allowed HTTPS host")
    destination = (
        root
        / "raw"
        / "natural_earth"
        / "admin0"
        / "v5.1.1"
        / "ne_10m_admin_0_countries.zip"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and zipfile.is_zipfile(destination):
        return destination
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    size = 0
    try:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=httpx.Timeout(300, connect=30),
            headers={"User-Agent": "weather-platform-smoke-validation/1.0"},
        ) as response:
            response.raise_for_status()
            if response.url.host != BOUNDARY_HOST:
                raise ValueError("Natural Earth boundary redirected outside the allowed host")
            with temporary.open("xb") as output:
                for block in response.iter_bytes(1024 * 1024):
                    size += len(block)
                    if size > 20 * 1024**2:
                        raise ValueError("Natural Earth boundary exceeds the size bound")
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
        if size == 0 or not zipfile.is_zipfile(temporary):
            raise ValueError("Natural Earth response is not a non-empty ZIP archive")
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _extract_canada_geometry(root: Path, archive: Path) -> Path:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise FileNotFoundError("ogr2ogr is required to extract the Canada boundary")
    destination = (
        root
        / "processed"
        / "natural_earth"
        / "admin0"
        / "v5.1.1"
        / "canada.geojson"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    source = (
        f"/vsizip/{archive.resolve().as_posix()}/"
        "ne_10m_admin_0_countries.shp"
    )
    process = subprocess.run(
        [
            ogr2ogr,
            "-overwrite",
            "-f",
            "GeoJSON",
            temporary.as_posix(),
            source,
            "-where",
            "ADM0_A3 = 'CAN'",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if process.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Natural Earth extraction failed: {process.stderr[-1000:]}")
    payload = json.loads(temporary.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("ADM0_A3") != "CAN":
        temporary.unlink(missing_ok=True)
        raise ValueError("Natural Earth extraction did not return exactly Canada")
    geometry_type = features[0].get("geometry", {}).get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        temporary.unlink(missing_ok=True)
        raise ValueError("Natural Earth Canada geometry is not polygonal")
    os.replace(temporary, destination)
    return destination


def _point_on_segment(
    longitude: float,
    latitude: float,
    left: list[float],
    right: list[float],
) -> bool:
    cross = (longitude - left[0]) * (right[1] - left[1]) - (
        latitude - left[1]
    ) * (right[0] - left[0])
    if abs(cross) > 1e-10:
        return False
    return (
        min(left[0], right[0]) - 1e-10
        <= longitude
        <= max(left[0], right[0]) + 1e-10
        and min(left[1], right[1]) - 1e-10
        <= latitude
        <= max(left[1], right[1]) + 1e-10
    )


def _inside_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(longitude, latitude, previous, current):
            return True
        if (current[1] > latitude) != (previous[1] > latitude):
            intersection = (previous[0] - current[0]) * (
                latitude - current[1]
            ) / (previous[1] - current[1]) + current[0]
            if longitude < intersection:
                inside = not inside
        previous = current
    return inside


def _compiled_polygons(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    geometry = payload["features"][0]["geometry"]
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    compiled = []
    for polygon in polygons:
        exterior = polygon[0]
        longitudes = [float(value[0]) for value in exterior]
        latitudes = [float(value[1]) for value in exterior]
        compiled.append(
            {
                "bbox": (
                    min(longitudes),
                    min(latitudes),
                    max(longitudes),
                    max(latitudes),
                ),
                "rings": polygon,
            }
        )
    return compiled


def _inside_canada(
    longitude: float,
    latitude: float,
    polygons: list[dict[str, Any]],
) -> bool:
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("hotspot coordinates must be finite")
    for polygon in polygons:
        west, south, east, north = polygon["bbox"]
        if not (west <= longitude <= east and south <= latitude <= north):
            continue
        rings = polygon["rings"]
        if _inside_ring(longitude, latitude, rings[0]) and not any(
            _inside_ring(longitude, latitude, hole) for hole in rings[1:]
        ):
            return True
    return False


def _load_detections(
    root: Path,
    start: date,
    end: date,
    polygons: list[dict[str, Any]],
    crosswalk_path: Path,
) -> tuple[list[Detection], dict[str, Any]]:
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk = {
        str(key).upper(): str(value).upper()
        for key, value in crosswalk_payload["rules"].items()
    }
    detections: dict[str, Detection] = {}
    exclusions: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    fuel_counts: Counter[str] = Counter()
    source_records = []
    gaps = []
    raw_feature_count = 0
    for day in _dates(start, end):
        directory = (
            root
            / "processed"
            / "nrcan"
            / "cwfis"
            / "firem3"
            / f"{day:%Y/%m/%d}"
        )
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            gaps.append(day)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = manifest["geojson"]
        geojson_path = root / record["relative_path"]
        if geojson_path.stat().st_size != record["size_bytes"] or _sha256(
            geojson_path
        ) != record["sha256"]:
            raise ValueError(f"CWFIS GeoJSON does not match its manifest: {geojson_path}")
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        raw_feature_count += len(features)
        source_records.append(
            {
                "date": day.isoformat(),
                "manifest_path": manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": _sha256(manifest_path),
                "geojson_relative_path": record["relative_path"],
                "geojson_sha256": record["sha256"],
                "feature_count": len(features),
            }
        )
        for feature in features:
            properties = dict(feature["properties"])
            longitude, latitude = (float(value) for value in feature["geometry"]["coordinates"])
            if not _inside_canada(longitude, latitude, polygons):
                exclusions["outside_canada_boundary"] += 1
                continue
            fuel_text = str(properties.get("fuel") or "")
            resolved = resolve_fbp_fuel(fuel_text, crosswalk)
            if resolved is None:
                exclusions[f"unsupported_fuel:{fuel_text or 'blank'}"] += 1
                continue
            detection_id = str(properties["detection_id"])
            observed = datetime.fromisoformat(
                str(properties["observed_at"]).replace("Z", "+00:00")
            ).astimezone(UTC)
            properties["model_fuel"] = resolved.model_code
            candidate = Detection(
                detection_id=detection_id,
                observed_at=observed,
                latitude=latitude,
                longitude=longitude,
                fuel=resolved.model_code,
                properties=properties,
            )
            existing = detections.get(detection_id)
            if existing is not None and existing != candidate:
                raise ValueError(f"conflicting duplicate detection: {detection_id}")
            if existing is not None:
                exclusions["exact_duplicate_detection"] += 1
                continue
            detections[detection_id] = candidate
            date_counts[day.isoformat()] += 1
            fuel_counts[resolved.model_code] += 1
    if set(gaps) != set(EXPECTED_HOTSPOT_GAPS):
        raise ValueError(f"unexpected CWFIS hotspot gaps: {[value.isoformat() for value in gaps]}")
    return sorted(detections.values(), key=lambda item: item.detection_id), {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "source_available_date_count": len(source_records),
        "source_gaps": [value.isoformat() for value in gaps],
        "raw_viirs_feature_count": raw_feature_count,
        "candidate_detection_count": len(detections),
        "date_counts": dict(sorted(date_counts.items())),
        "fuel_counts": dict(sorted(fuel_counts.items())),
        "exclusion_reasons": dict(sorted(exclusions.items())),
        "sources": source_records,
        "fuel_crosswalk": {
            "path": crosswalk_path.as_posix(),
            "sha256": _sha256(crosswalk_path),
            "version": crosswalk_payload["crosswalk_version"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--boundary-url", default=BOUNDARY_URL)
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
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("docs/smoke-validation-protocol-2026.md"),
    )
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve()
    archive = _download_boundary(root, args.boundary_url)
    canada_path = _extract_canada_geometry(root, archive)
    polygons = _compiled_polygons(canada_path)
    detections, detection_report = _load_detections(
        root,
        args.start,
        args.end,
        polygons,
        args.fuel_crosswalk,
    )
    config = EventMatchingConfig.from_yaml(args.event_config)
    events = reconcile_events(detections, config)
    events["source_hotspots"] = {
        "report_sha256": hashlib.sha256(
            json.dumps(detection_report, sort_keys=True).encode()
        ).hexdigest(),
    }

    output = args.output_directory.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "candidate-events.json"
    _atomic_json(events_path, events)
    report = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "events_frozen_pending_independent_area",
        "experiment_interval": {
            "start": args.start.isoformat(),
            "end_inclusive": args.end.isoformat(),
        },
        "protocol": {
            "path": args.protocol.as_posix(),
            "sha256": _sha256(args.protocol),
        },
        "country_boundary": {
            "dataset": "Natural Earth Admin 0 Countries",
            "version": "5.1.1",
            "selection": "ADM0_A3=CAN",
            "source_url": args.boundary_url,
            "archive_relative_path": archive.relative_to(root).as_posix(),
            "archive_size_bytes": archive.stat().st_size,
            "archive_sha256": _sha256(archive),
            "canada_relative_path": canada_path.relative_to(root).as_posix(),
            "canada_size_bytes": canada_path.stat().st_size,
            "canada_sha256": _sha256(canada_path),
            "polygon_part_count": len(polygons),
        },
        "hotspots": detection_report,
        "event_reconciliation": {
            "configuration_path": args.event_config.as_posix(),
            "configuration_sha256": _sha256(args.event_config),
            "algorithm_version": config.algorithm_version,
            "event_count": events["event_count"],
            "detection_count": events["detection_count"],
            "events_path": events_path.as_posix(),
            "events_sha256": _sha256(events_path),
        },
        "scientific_candidate_run_started": False,
    }
    report_path = output / "event-ledger-report.json"
    _atomic_json(report_path, report)
    print(
        json.dumps(
            {
                "event_count": events["event_count"],
                "detection_count": events["detection_count"],
                "events_path": events_path.as_posix(),
                "events_sha256": _sha256(events_path),
                "report_path": report_path.as_posix(),
                "report_sha256": _sha256(report_path),
                "country_boundary_archive_sha256": _sha256(archive),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
