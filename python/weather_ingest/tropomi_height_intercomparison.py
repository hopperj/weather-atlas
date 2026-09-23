"""Frozen TROPOMI aerosol-height to FLEXPART PM2.5 matchup operator."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

EARTH_RADIUS_KM = 6371.0088


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
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _filled(variable: Any) -> np.ndarray:
    return np.asarray(np.ma.filled(variable[:], np.nan), dtype=np.float64)


def _haversine_km(
    latitude: np.ndarray,
    longitude: np.ndarray,
    event_latitude: float,
    event_longitude: float,
) -> np.ndarray:
    lat1 = np.radians(latitude)
    lat2 = math.radians(event_latitude)
    delta_lat = lat1 - lat2
    delta_lon = np.radians(longitude - event_longitude)
    haversine = np.sin(delta_lat / 2.0) ** 2 + (
        np.cos(lat1) * math.cos(lat2) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(
        np.sqrt(np.clip(haversine, 0.0, 1.0))
    )


def _layer_geometry(upper_boundaries_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    upper = np.asarray(upper_boundaries_m, dtype=np.float64)
    if upper.ndim != 1 or upper.size == 0:
        raise ValueError("FLEXPART output heights must be a non-empty vector")
    lower = np.concatenate(([0.0], upper[:-1]))
    thickness = upper - lower
    if not np.all(np.isfinite(upper)) or np.any(thickness <= 0):
        raise ValueError("FLEXPART output heights must be finite and increasing")
    return (lower + upper) / 2.0, thickness


def _mass_weighted_height(
    concentration: np.ndarray,
    upper_boundaries_m: np.ndarray,
) -> tuple[float | None, float]:
    profile = np.asarray(concentration, dtype=np.float64)
    midpoints, thickness = _layer_geometry(upper_boundaries_m)
    if profile.shape != midpoints.shape:
        raise ValueError("concentration profile does not match the vertical grid")
    if not np.all(np.isfinite(profile)) or np.any(profile < 0):
        raise ValueError("FLEXPART concentration profile is invalid")
    column_weight = profile * thickness
    total_weight = float(column_weight.sum())
    if total_weight <= 0:
        return None, total_weight
    return float(np.dot(column_weight, midpoints) / total_weight), total_weight


def _containing_cell(centres: np.ndarray, value: float) -> int | None:
    coordinates = np.asarray(centres, dtype=np.float64)
    if coordinates.ndim != 1 or coordinates.size < 2:
        raise ValueError("grid coordinates must have at least two cells")
    increments = np.diff(coordinates)
    if not np.allclose(increments, increments[0], rtol=0, atol=1e-7):
        raise ValueError("only regular FLEXPART output grids are supported")
    increment = float(increments[0])
    if increment <= 0:
        raise ValueError("FLEXPART output coordinates must increase")
    lower = float(coordinates[0] - increment / 2.0)
    index = int(math.floor((value - lower) / increment))
    return index if 0 <= index < coordinates.size else None


def _parse_time(value: object) -> datetime:
    text = (
        value.decode("utf-8")
        if isinstance(value, bytes)
        else str(value)
    ).strip()
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _load_events(input_manifest: Path) -> tuple[dict[date, list[dict[str, Any]]], dict[str, Any]]:
    payload = json.loads(input_manifest.read_text(encoding="utf-8"))
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for event in payload["events"]:
        for day_text in event["daily_increment_ha"]:
            by_day[date.fromisoformat(day_text)].append(
                {
                    "event_id": event["event_id"],
                    "latitude": float(event["latitude"]),
                    "longitude": float(event["longitude"]),
                }
            )
    return by_day, {
        "path": input_manifest.as_posix(),
        "size_bytes": input_manifest.stat().st_size,
        "sha256": _sha256(input_manifest),
    }


def _model_path(candidate_directory: Path, day: date) -> Path:
    matches = sorted(
        (
            candidate_directory
            / "transport"
            / day.isoformat()
            / "pm25"
            / "output"
        ).glob("grid_conc_*.nc")
    )
    if len(matches) != 1:
        raise ValueError(f"expected one PM2.5 FLEXPART output for {day}, found {len(matches)}")
    return matches[0]


def _load_model(path: Path) -> dict[str, Any]:
    dataset = netCDF4.Dataset(path)
    required = {"time", "longitude", "latitude", "height", "spec001_mr"}
    missing = required.difference(dataset.variables)
    if missing:
        dataset.close()
        raise ValueError(f"FLEXPART output lacks variables: {sorted(missing)}")
    time_variable = dataset.variables["time"]
    model_times = [
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        for value in netCDF4.num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
    ]
    return {
        "dataset": dataset,
        "times": model_times,
        "longitude": _filled(dataset.variables["longitude"]),
        "latitude": _filled(dataset.variables["latitude"]),
        "height": _filled(dataset.variables["height"]),
        "concentration": dataset.variables["spec001_mr"],
        "provenance": {
            "path": path.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
    }


def _write_pairs(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "observed",
        "modelled",
        "observation_time_utc",
        "model_time_utc",
        "time_offset_minutes",
        "latitude",
        "longitude",
        "event_id",
        "distance_to_event_km",
        "qa_value",
        "aerosol_mid_height_asl_m",
        "surface_altitude_m",
        "flexpart_column_weight_ng_m2",
        "flexpart_latitude_index",
        "flexpart_longitude_index",
        "source_granule",
        "scanline",
        "ground_pixel",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "pair_count": len(rows),
    }


def build_tropomi_height_pairs(
    *,
    candidate_directory: Path,
    tropomi_root: Path,
    output_directory: Path,
    qa_minimum: float = 0.5,
    event_radius_km: float = 50.0,
    maximum_time_offset_minutes: float = 90.0,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Match frozen source-day TROPOMI pixels to FLEXPART PM2.5 column heights."""

    if not 0 <= qa_minimum <= 1:
        raise ValueError("qa minimum must be between zero and one")
    if event_radius_km <= 0 or maximum_time_offset_minutes < 0:
        raise ValueError("spatial and temporal tolerances must be non-negative")
    input_manifest = candidate_directory / "input-manifest.json"
    events_by_day, input_source = _load_events(input_manifest)
    if not events_by_day:
        raise ValueError("candidate input manifest has no source days")

    rows: list[dict[str, Any]] = []
    granule_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    for day in sorted(events_by_day):
        model = _load_model(_model_path(candidate_directory, day))
        model_records.append(model["provenance"])
        dataset = model["dataset"]
        try:
            granules = sorted((tropomi_root / day.strftime("%Y/%m/%d")).glob("*.nc"))
            if not granules:
                raise FileNotFoundError(f"no TROPOMI granules found for {day}")
            for granule_index, granule in enumerate(granules, start=1):
                print(
                    f"TROPOMI {day} granule {granule_index}/{len(granules)}",
                    flush=True,
                )
                counts: Counter[str] = Counter()
                with netCDF4.Dataset(granule) as satellite:
                    product = satellite.groups["PRODUCT"]
                    latitude = _filled(product.variables["latitude"])[0]
                    longitude = _filled(product.variables["longitude"])[0]
                    qa = _filled(product.variables["qa_value"])[0]
                    aerosol_asl = _filled(product.variables["aerosol_mid_height"])[0]
                    input_data = product.groups["SUPPORT_DATA"].groups["INPUT_DATA"]
                    surface = _filled(input_data.variables["surface_altitude"])[0]
                    scanline_times = [
                        _parse_time(value)
                        for value in product.variables["time_utc"][0, :].tolist()
                    ]

                    nearest_distance = np.full(latitude.shape, np.inf)
                    nearest_event = np.full(latitude.shape, -1, dtype=np.int16)
                    for event_index, event in enumerate(events_by_day[day]):
                        distance = _haversine_km(
                            latitude,
                            longitude,
                            event["latitude"],
                            event["longitude"],
                        )
                        replace = distance < nearest_distance
                        nearest_distance[replace] = distance[replace]
                        nearest_event[replace] = event_index
                    spatial = nearest_distance <= event_radius_km
                    counts["pixels_total"] = int(latitude.size)
                    counts["within_event_radius"] = int(spatial.sum())
                    quality = spatial & np.isfinite(qa) & (qa >= qa_minimum)
                    counts["qa_accepted"] = int(quality.sum())
                    finite_height = (
                        quality
                        & np.isfinite(aerosol_asl)
                        & np.isfinite(surface)
                    )
                    counts["finite_height_accepted"] = int(finite_height.sum())

                    for scanline, ground_pixel in zip(
                        *np.nonzero(finite_height), strict=True
                    ):
                        observation_time = scanline_times[int(scanline)]
                        if observation_time.date() != day:
                            rejection_counts["pixel_observation_date_mismatch"] += 1
                            continue
                        offsets = np.asarray(
                            [
                                abs((model_time - observation_time).total_seconds())
                                for model_time in model["times"]
                            ]
                        )
                        time_index = int(np.argmin(offsets))
                        offset_minutes = float(offsets[time_index] / 60.0)
                        if offset_minutes > maximum_time_offset_minutes:
                            rejection_counts["no_model_time_within_tolerance"] += 1
                            continue
                        pixel_latitude = float(latitude[scanline, ground_pixel])
                        pixel_longitude = float(longitude[scanline, ground_pixel])
                        latitude_index = _containing_cell(
                            model["latitude"], pixel_latitude
                        )
                        longitude_index = _containing_cell(
                            model["longitude"], pixel_longitude
                        )
                        if latitude_index is None or longitude_index is None:
                            rejection_counts["outside_flexpart_grid"] += 1
                            continue
                        profile = np.asarray(
                            model["concentration"][
                                :,
                                :,
                                time_index,
                                :,
                                latitude_index,
                                longitude_index,
                            ],
                            dtype=np.float64,
                        ).sum(axis=(0, 1))
                        model_height, column_weight = _mass_weighted_height(
                            profile, model["height"]
                        )
                        if model_height is None:
                            rejection_counts["zero_model_column_mass"] += 1
                            continue
                        event = events_by_day[day][
                            int(nearest_event[scanline, ground_pixel])
                        ]
                        rows.append(
                            {
                                "observed": format(
                                    float(
                                        aerosol_asl[scanline, ground_pixel]
                                        - surface[scanline, ground_pixel]
                                    ),
                                    ".17g",
                                ),
                                "modelled": format(model_height, ".17g"),
                                "observation_time_utc": observation_time.isoformat().replace(
                                    "+00:00", "Z"
                                ),
                                "model_time_utc": model["times"][
                                    time_index
                                ].isoformat().replace("+00:00", "Z"),
                                "time_offset_minutes": format(
                                    offset_minutes, ".8f"
                                ),
                                "latitude": format(pixel_latitude, ".8f"),
                                "longitude": format(pixel_longitude, ".8f"),
                                "event_id": event["event_id"],
                                "distance_to_event_km": format(
                                    float(nearest_distance[scanline, ground_pixel]),
                                    ".8f",
                                ),
                                "qa_value": format(
                                    float(qa[scanline, ground_pixel]), ".8f"
                                ),
                                "aerosol_mid_height_asl_m": format(
                                    float(aerosol_asl[scanline, ground_pixel]), ".8f"
                                ),
                                "surface_altitude_m": format(
                                    float(surface[scanline, ground_pixel]), ".8f"
                                ),
                                "flexpart_column_weight_ng_m2": format(
                                    column_weight, ".17g"
                                ),
                                "flexpart_latitude_index": latitude_index,
                                "flexpart_longitude_index": longitude_index,
                                "source_granule": granule.name,
                                "scanline": int(scanline),
                                "ground_pixel": int(ground_pixel),
                            }
                        )
                        counts["paired"] += 1
                granule_records.append(
                    {
                        "path": granule.as_posix(),
                        "size_bytes": granule.stat().st_size,
                        "sha256": _sha256(granule),
                        "counts": dict(sorted(counts.items())),
                    }
                )
        finally:
            dataset.close()

    rows.sort(
        key=lambda row: (
            row["observation_time_utc"],
            row["event_id"],
            int(row["scanline"]),
            int(row["ground_pixel"]),
        )
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    pair_source = _write_pairs(
        output_directory / "tropomi-aer-lh-pm25-height-pairs.csv", rows
    )
    report = {
        "schema_version": 1,
        "product": "tropomi_aer_lh_flexpart_pm25_height_pairs",
        "assessment_role": "diagnostic_vertical_intercomparison",
        "acceptance_capable": False,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "command": command if command is not None else sys.argv,
        "operator": {
            "qa_minimum_inclusive": qa_minimum,
            "event_radius_km_inclusive": event_radius_km,
            "maximum_time_offset_minutes_inclusive": maximum_time_offset_minutes,
            "observed_height": (
                "TROPOMI aerosol_mid_height relative to geoid minus "
                "TROPOMI Copernicus DEM surface_altitude"
            ),
            "model_height": (
                "FLEXPART PM2.5 concentration times layer thickness weighted "
                "mean of layer midpoint AGL heights"
            ),
            "flexpart_vertical_coordinate": (
                "NetCDF height values interpreted as upper layer boundaries, "
                "consistent with FLEXPART OUTGRID"
            ),
            "cell_assignment": "containing_regular_flexpart_grid_cell_v1",
            "time_assignment": "nearest_flexpart_interval_end_v1",
        },
        "candidate_input_manifest": input_source,
        "source_days": [day.isoformat() for day in sorted(events_by_day)],
        "model_outputs": model_records,
        "tropomi_granules": granule_records,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "pairs": pair_source,
        "sample_sufficient_for_frozen_gate": len(rows) >= 20,
    }
    manifest_path = output_directory / "manifest.json"
    _atomic_json(manifest_path, report)
    return report | {
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": _sha256(manifest_path),
    }
