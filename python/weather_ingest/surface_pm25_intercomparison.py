"""Frozen AirNow/AQS surface-PM2.5 to FLEXPART matchup operators."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np


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


def _containing_cell(centres: np.ndarray, value: float) -> int | None:
    coordinates = np.asarray(centres, dtype=np.float64)
    increments = np.diff(coordinates)
    if coordinates.ndim != 1 or coordinates.size < 2:
        raise ValueError("grid coordinates must have at least two cells")
    if not np.allclose(increments, increments[0], rtol=0, atol=1e-7):
        raise ValueError("only regular FLEXPART output grids are supported")
    increment = float(increments[0])
    lower = float(coordinates[0] - increment / 2.0)
    index = int(math.floor((value - lower) / increment))
    return index if 0 <= index < coordinates.size else None


def _model_path(candidate_directory: Path, day: date) -> Path:
    matches = sorted(
        (candidate_directory / "transport" / day.isoformat() / "pm25" / "output").glob(
            "grid_conc_*.nc"
        )
    )
    if len(matches) != 1:
        raise ValueError(f"expected one PM2.5 FLEXPART output for {day}, found {len(matches)}")
    return matches[0]


def _python_datetimes(variable: Any) -> list[datetime]:
    return [
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        for value in netCDF4.num2date(
            variable[:],
            units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
    ]


def _load_candidate_model(candidate_directory: Path) -> dict[str, Any]:
    manifest_path = candidate_directory / "input-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_days = sorted(date.fromisoformat(value) for value in manifest["source_days"])
    event_ids_by_source_day: dict[date, list[str]] = {
        day: sorted(
            str(event["event_id"])
            for event in manifest.get("events", [])
            if day.isoformat() in event.get("daily_increment_ha", {})
        )
        for day in source_days
    }
    model_by_time: dict[datetime, np.ndarray] = {}
    source_day_by_time: dict[datetime, date] = {}
    provenance: list[dict[str, Any]] = []
    longitude: np.ndarray | None = None
    latitude: np.ndarray | None = None
    surface_layer_upper_m: float | None = None
    for day in source_days:
        path = _model_path(candidate_directory, day)
        with netCDF4.Dataset(path) as dataset:
            current_longitude = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
            current_latitude = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
            current_surface_layer_upper_m = float(dataset.variables["height"][0])
            if longitude is None:
                longitude = current_longitude
                latitude = current_latitude
                surface_layer_upper_m = current_surface_layer_upper_m
            elif not (
                np.array_equal(longitude, current_longitude)
                and np.array_equal(latitude, current_latitude)
            ):
                raise ValueError("FLEXPART surface grid changes between source days")
            elif not math.isclose(
                float(surface_layer_upper_m),
                current_surface_layer_upper_m,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                raise ValueError("FLEXPART surface layer changes between source days")
            times = _python_datetimes(dataset.variables["time"])
            concentration = np.asarray(
                np.ma.filled(dataset.variables["spec001_mr"][:, :, :, 0, :, :], np.nan),
                dtype=np.float64,
            ).sum(axis=(0, 1))
            if concentration.shape[0] != len(times):
                raise ValueError("FLEXPART time and concentration dimensions disagree")
            if not np.all(np.isfinite(concentration)) or np.any(concentration < 0):
                raise ValueError(f"invalid FLEXPART surface concentration in {path}")
            for index, timestamp in enumerate(times):
                if timestamp in model_by_time:
                    raise ValueError(f"duplicate candidate model time: {timestamp}")
                model_by_time[timestamp] = concentration[index] / 1000.0
                source_day_by_time[timestamp] = day
        provenance.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    assert longitude is not None and latitude is not None
    return {
        "source_days": source_days,
        "model_by_time": model_by_time,
        "source_day_by_time": source_day_by_time,
        "event_ids_by_source_day": event_ids_by_source_day,
        "longitude": longitude,
        "latitude": latitude,
        "surface_layer_upper_m": surface_layer_upper_m,
        "provenance": provenance,
        "input_manifest": {
            "path": manifest_path.as_posix(),
            "size_bytes": manifest_path.stat().st_size,
            "sha256": _sha256(manifest_path),
        },
    }


def _active_cells(model: dict[str, Any], threshold: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for field in model["model_by_time"].values():
        rows, columns = np.nonzero(field >= threshold)
        cells.update(zip(rows.tolist(), columns.tolist(), strict=True))
    return cells


def _register_observation(
    *,
    observations: dict[tuple[str, datetime], float],
    metadata: dict[str, dict[str, Any]],
    key: str,
    timestamp: datetime,
    value: float,
    station_metadata: dict[str, Any],
) -> None:
    existing = observations.get((key, timestamp))
    if existing is not None:
        if not math.isclose(existing, value, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"conflicting duplicate observation for {key} at {timestamp}")
        return
    existing_metadata = metadata.get(key)
    if existing_metadata is not None and (
        not math.isclose(
            float(existing_metadata["latitude"]),
            float(station_metadata["latitude"]),
            rel_tol=0,
            abs_tol=1e-5,
        )
        or not math.isclose(
            float(existing_metadata["longitude"]),
            float(station_metadata["longitude"]),
            rel_tol=0,
            abs_tol=1e-5,
        )
    ):
        raise ValueError(f"station coordinates change for {key}")
    observations[(key, timestamp)] = value
    metadata.setdefault(key, station_metadata)


def _input_manifest_records(paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": path.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in paths
    ]


def _read_airnow(
    *,
    root: Path,
    start: date,
    end: date,
    longitude: np.ndarray,
    latitude: np.ndarray,
    active_cells: set[tuple[int, int]],
    input_manifests: list[Path],
) -> dict[str, Any]:
    observations: dict[tuple[str, datetime], float] = {}
    metadata: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    file_set_digest = hashlib.sha256()
    total_bytes = 0
    day = start
    while day <= end:
        for hour in range(24):
            timestamp = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            path = root / f"{day:%Y/%m/%d}" / f"HourlyAQObs_{timestamp:%Y%m%d%H}.dat"
            if not path.is_file():
                raise FileNotFoundError(path)
            checksum = _sha256(path)
            file_set_digest.update(f"{path.relative_to(root).as_posix()}\\0{checksum}\\n".encode())
            total_bytes += path.stat().st_size
            counts["source_files"] += 1
            with path.open(newline="", encoding="utf-8-sig") as source:
                for row in csv.DictReader(source):
                    counts["rows_total"] += 1
                    if (
                        row["CountryCode"].strip() != "CA"
                        or row["PM25_Measured"].strip() != "1"
                        or row["PM25_Unit"].strip().upper() != "UG/M3"
                        or not row["PM25"].strip()
                    ):
                        continue
                    try:
                        value = float(row["PM25"])
                        station_latitude = float(row["Latitude"])
                        station_longitude = float(row["Longitude"])
                    except ValueError:
                        counts["nonfinite_or_invalid"] += 1
                        continue
                    if not all(
                        math.isfinite(item) for item in (value, station_latitude, station_longitude)
                    ):
                        counts["nonfinite_or_invalid"] += 1
                        continue
                    row_timestamp = datetime.strptime(
                        f"{row['ValidDate']} {row['ValidTime']}", "%m/%d/%Y %H:%M"
                    ).replace(tzinfo=UTC)
                    if row_timestamp != timestamp:
                        raise ValueError(f"AirNow row time disagrees with filename: {path}")
                    latitude_index = _containing_cell(latitude, station_latitude)
                    longitude_index = _containing_cell(longitude, station_longitude)
                    if latitude_index is None or longitude_index is None:
                        counts["outside_model_grid"] += 1
                        continue
                    if (latitude_index, longitude_index) not in active_cells:
                        counts["outside_active_model_cells"] += 1
                        continue
                    key = row["AQSID"].strip()
                    if not key:
                        raise ValueError(f"AirNow PM2.5 row lacks AQSID: {path}")
                    _register_observation(
                        observations=observations,
                        metadata=metadata,
                        key=key,
                        timestamp=timestamp,
                        value=value,
                        station_metadata={
                            "station_key": key,
                            "site_name": row["SiteName"].strip(),
                            "latitude": station_latitude,
                            "longitude": station_longitude,
                            "network": "AirNow",
                        },
                    )
                    counts["eligible_rows_in_active_cells"] += 1
        day += timedelta(days=1)
    return {
        "observations": observations,
        "metadata": metadata,
        "provenance": {
            "network": "AirNow",
            "interval": {
                "start": start.isoformat(),
                "end_inclusive": end.isoformat(),
            },
            "file_count": counts["source_files"],
            "total_bytes": total_bytes,
            "file_set_sha256": file_set_digest.hexdigest(),
            "input_manifests": _input_manifest_records(input_manifests),
            "counts": dict(sorted(counts.items())),
        },
    }


def _read_aqs(
    *,
    archives: list[Path],
    start: date,
    end: date,
    longitude: np.ndarray,
    latitude: np.ndarray,
    active_cells: set[tuple[int, int]],
    input_manifest: Path,
) -> dict[str, Any]:
    observations: dict[tuple[str, datetime], float] = {}
    metadata: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    archive_records: list[dict[str, Any]] = []
    for path in archives:
        print(f"AQS reading {path.name}", flush=True)
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
            if len(members) != 1:
                raise ValueError(f"expected one CSV member in {path}")
            with archive.open(members[0]) as raw:
                source = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                for row in csv.DictReader(source):
                    counts["rows_total"] += 1
                    day_text = row["Date GMT"].strip()
                    if not start.isoformat() <= day_text <= end.isoformat():
                        continue
                    if (
                        row["Parameter Code"].strip() not in {"88101", "88502"}
                        or row["Units of Measure"].strip() != "Micrograms/cubic meter (LC)"
                        or row["Qualifier"].strip()
                    ):
                        counts["quality_or_unit_rejected"] += 1
                        continue
                    try:
                        value = float(row["Sample Measurement"])
                        station_latitude = float(row["Latitude"])
                        station_longitude = float(row["Longitude"])
                        timestamp = datetime.fromisoformat(
                            f"{day_text}T{row['Time GMT'].strip()}:00+00:00"
                        ).astimezone(UTC)
                    except ValueError:
                        counts["nonfinite_or_invalid"] += 1
                        continue
                    if not all(
                        math.isfinite(item) for item in (value, station_latitude, station_longitude)
                    ):
                        counts["nonfinite_or_invalid"] += 1
                        continue
                    latitude_index = _containing_cell(latitude, station_latitude)
                    longitude_index = _containing_cell(longitude, station_longitude)
                    if latitude_index is None or longitude_index is None:
                        counts["outside_model_grid"] += 1
                        continue
                    if (latitude_index, longitude_index) not in active_cells:
                        counts["outside_active_model_cells"] += 1
                        continue
                    parts = (
                        row["State Code"].strip(),
                        row["County Code"].strip(),
                        row["Site Num"].strip(),
                        row["Parameter Code"].strip(),
                        row["POC"].strip(),
                    )
                    if any(not part for part in parts):
                        raise ValueError(f"AQS row has incomplete monitor key in {path}")
                    key = "-".join(parts)
                    _register_observation(
                        observations=observations,
                        metadata=metadata,
                        key=key,
                        timestamp=timestamp,
                        value=value,
                        station_metadata={
                            "station_key": key,
                            "site_name": (
                                f"{row['County Name'].strip()}, {row['State Name'].strip()}"
                            ),
                            "latitude": station_latitude,
                            "longitude": station_longitude,
                            "network": "AQS",
                            "parameter_code": parts[3],
                            "poc": parts[4],
                        },
                    )
                    counts["eligible_rows_in_active_cells"] += 1
        archive_records.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "member": members[0],
            }
        )
    return {
        "observations": observations,
        "metadata": metadata,
        "provenance": {
            "network": "US EPA AQS",
            "interval": {
                "start": start.isoformat(),
                "end_inclusive": end.isoformat(),
            },
            "archives": archive_records,
            "input_manifest": _input_manifest_records([input_manifest])[0],
            "counts": dict(sorted(counts.items())),
        },
    }


def _write_pairs(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "observed",
        "modelled",
        "observation_time_utc",
        "station_key",
        "site_name",
        "network",
        "latitude",
        "longitude",
        "raw_pm25_ug_m3",
        "background_pm25_ug_m3",
        "background_statistic",
        "background_value_count",
        "flexpart_latitude_index",
        "flexpart_longitude_index",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "pair_count": len(rows),
    }


def _match(
    *,
    source: dict[str, Any],
    model: dict[str, Any],
    background_window_days: int,
    minimum_background_values: int,
    model_minimum: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    observations = source["observations"]
    metadata = source["metadata"]
    by_monitor_hour: dict[tuple[str, int], dict[date, float]] = defaultdict(dict)
    by_timestamp: dict[datetime, list[tuple[str, float]]] = defaultdict(list)
    for (key, timestamp), value in observations.items():
        by_monitor_hour[(key, timestamp.hour)][timestamp.date()] = value
        by_timestamp[timestamp].append((key, value))

    source_dates = set(model["source_days"])
    central_rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    for timestamp, field in sorted(model["model_by_time"].items()):
        target_observations = by_timestamp.get(timestamp, [])
        if not target_observations:
            rejections["model_hours_without_observations_in_active_cells"] += 1
        for key, raw_value in target_observations:
            station = metadata[key]
            latitude_index = _containing_cell(model["latitude"], float(station["latitude"]))
            longitude_index = _containing_cell(model["longitude"], float(station["longitude"]))
            assert latitude_index is not None and longitude_index is not None
            modelled = float(field[latitude_index, longitude_index])
            if modelled < model_minimum:
                rejections["below_model_pair_threshold"] += 1
                continue
            background = [
                value
                for background_date, value in by_monitor_hour[(key, timestamp.hour)].items()
                if background_date != timestamp.date()
                and background_date not in source_dates
                and abs((background_date - timestamp.date()).days) <= background_window_days
            ]
            if len(background) < minimum_background_values:
                rejections["insufficient_background"] += 1
                continue
            central_background = float(np.median(background))
            sensitivity_background = float(np.percentile(background, 20.0, method="linear"))
            common = {
                "modelled": format(modelled, ".17g"),
                "observation_time_utc": timestamp.isoformat().replace("+00:00", "Z"),
                "station_key": key,
                "site_name": station["site_name"],
                "network": station["network"],
                "latitude": format(float(station["latitude"]), ".8f"),
                "longitude": format(float(station["longitude"]), ".8f"),
                "raw_pm25_ug_m3": format(raw_value, ".17g"),
                "background_value_count": len(background),
                "flexpart_latitude_index": latitude_index,
                "flexpart_longitude_index": longitude_index,
            }
            central_rows.append(
                {
                    **common,
                    "observed": format(max(raw_value - central_background, 0.0), ".17g"),
                    "background_pm25_ug_m3": format(central_background, ".17g"),
                    "background_statistic": "median",
                }
            )
            sensitivity_rows.append(
                {
                    **common,
                    "observed": format(max(raw_value - sensitivity_background, 0.0), ".17g"),
                    "background_pm25_ug_m3": format(sensitivity_background, ".17g"),
                    "background_statistic": "20th_percentile_numpy_linear",
                }
            )

    def sort_key(row: dict[str, Any]) -> tuple[str, str]:
        return row["observation_time_utc"], row["station_key"]

    central_rows.sort(key=sort_key)
    sensitivity_rows.sort(key=sort_key)
    return central_rows, sensitivity_rows, dict(sorted(rejections.items()))


def build_surface_pm25_pairs(
    *,
    network: str,
    candidate_directory: Path,
    output_directory: Path,
    airnow_root: Path | None = None,
    airnow_manifests: list[Path] | None = None,
    aqs_archives: list[Path] | None = None,
    aqs_manifest: Path | None = None,
    background_window_days: int = 14,
    minimum_background_values: int = 7,
    model_minimum_ug_m3: float = 0.01,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Create central and 20th-percentile surface PM2.5 pair sets."""

    if network not in {"airnow", "aqs"}:
        raise ValueError("network must be airnow or aqs")
    model = _load_candidate_model(candidate_directory)
    active_cells = _active_cells(model, model_minimum_ug_m3)
    model_times = sorted(model["model_by_time"])
    observation_start = model_times[0].date() - timedelta(days=background_window_days)
    observation_end = model_times[-1].date() + timedelta(days=background_window_days)
    if network == "airnow":
        if airnow_root is None or not airnow_manifests:
            raise ValueError("AirNow root and manifests are required")
        source = _read_airnow(
            root=airnow_root,
            start=observation_start,
            end=observation_end,
            longitude=model["longitude"],
            latitude=model["latitude"],
            active_cells=active_cells,
            input_manifests=airnow_manifests,
        )
    else:
        if not aqs_archives or aqs_manifest is None:
            raise ValueError("AQS archives and manifest are required")
        source = _read_aqs(
            archives=aqs_archives,
            start=observation_start,
            end=observation_end,
            longitude=model["longitude"],
            latitude=model["latitude"],
            active_cells=active_cells,
            input_manifest=aqs_manifest,
        )
    central, sensitivity, rejections = _match(
        source=source,
        model=model,
        background_window_days=background_window_days,
        minimum_background_values=minimum_background_values,
        model_minimum=model_minimum_ug_m3,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    central_source = _write_pairs(
        output_directory / f"{network}-pm25-median-background-pairs.csv", central
    )
    sensitivity_source = _write_pairs(
        output_directory / f"{network}-pm25-p20-background-pairs.csv", sensitivity
    )
    report = {
        "schema_version": 1,
        "product": f"{network}_flexpart_surface_pm25_pairs",
        "assessment_role": (
            "provisional_independent_surface_observation_test"
            if network == "airnow"
            else "provisional_regulatory_surface_observation_test"
        ),
        "acceptance_capable": False,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "command": command if command is not None else sys.argv,
        "operator": {
            "background_window_days_each_side": background_window_days,
            "background_same_utc_hour": True,
            "candidate_dates_excluded_from_background": [
                day.isoformat() for day in model["source_days"]
            ],
            "minimum_background_values": minimum_background_values,
            "central_background": "median",
            "sensitivity_background": "20th_percentile_numpy_linear",
            "observed_enhancement": "max(raw_pm25_minus_background,0)",
            "model_quantity": "FLEXPART_0_50m_PM25_ng_m3_divided_by_1000",
            "model_pair_minimum_ug_m3_inclusive": model_minimum_ug_m3,
            "cell_assignment": "containing_regular_flexpart_grid_cell_v1",
        },
        "candidate_input_manifest": model["input_manifest"],
        "model_outputs": model["provenance"],
        "model_time_count": len(model["model_by_time"]),
        "active_model_cell_count": len(active_cells),
        "observation_source": source["provenance"],
        "rejection_counts": rejections,
        "central_pairs": central_source,
        "sensitivity_pairs": sensitivity_source,
        "central_sample_sufficient_for_frozen_gate": len(central) >= 100,
    }
    manifest_path = output_directory / "manifest.json"
    _atomic_json(manifest_path, report)
    return report | {
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": _sha256(manifest_path),
    }
