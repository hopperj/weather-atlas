"""Parser for final NAPS hourly PM2.5 archives."""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NapsPm25Observation:
    station_id: str
    method_code: str
    city: str
    province: str
    latitude: float
    longitude: float
    interval_end_utc: datetime
    value_ug_m3: float


PROVINCE_STANDARD_UTC_OFFSET_HOURS = {
    "BC": -8.0,
    "AB": -7.0,
    "SK": -6.0,
    "MB": -6.0,
    "ON": -5.0,
    "QC": -5.0,
    "NB": -4.0,
    "NS": -4.0,
    "PE": -4.0,
    "NL": -3.5,
    "YT": -7.0,
    "YU": -7.0,
    "NT": -7.0,
}


def _standard_offset(province: str, longitude: float) -> float:
    value = PROVINCE_STANDARD_UTC_OFFSET_HOURS.get(province.upper())
    if value is not None:
        return value
    if province.upper() == "NU":
        if longitude < -102:
            return -7.0
        if longitude < -85:
            return -6.0
        return -5.0
    raise ValueError(f"unsupported NAPS province/territory: {province}")


def _header_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if "NAPS ID//" in line and "H01//" in line:
            return index
    raise ValueError("NAPS archive lacks the bilingual hourly header")


def _utc_interval_end(
    day: date,
    hour_ending: int,
    *,
    standard_offset_hours: float,
) -> datetime:
    local_midnight = datetime(day.year, day.month, day.day)
    local_end = local_midnight + timedelta(hours=hour_ending)
    local_zone = timezone(timedelta(hours=standard_offset_hours))
    return local_end.replace(tzinfo=local_zone).astimezone(UTC)


def read_naps_pm25(
    path: Path,
    *,
    choose_primary_method: bool = True,
) -> tuple[list[NapsPm25Observation], dict[str, object]]:
    """Read final NAPS hour-ending local-standard-time PM2.5 into UTC."""

    lines = path.read_text(encoding="utf-8-sig", errors="strict").splitlines()
    header_index = _header_index(lines)
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    observations: list[NapsPm25Observation] = []
    method_counts: Counter[tuple[str, str]] = Counter()
    station_coordinates: dict[str, tuple[float, float]] = {}
    invalid_count = 0
    for row in reader:
        station_id = row["NAPS ID//Identifiant SNPA"].strip()
        method_code = row["Method Code//Code Méthode"].strip()
        province = row["Province/Territory//Province/Territoire"].strip()
        latitude = float(row["Latitude//Latitude"])
        longitude = float(row["Longitude//Longitude"])
        if not station_id or not all(math.isfinite(item) for item in (latitude, longitude)):
            raise ValueError("NAPS row has invalid station identity or coordinates")
        previous = station_coordinates.setdefault(station_id, (latitude, longitude))
        if previous != (latitude, longitude):
            raise ValueError(
                f"NAPS station {station_id} changes coordinates; freeze a station history first"
            )
        day = date.fromisoformat(row["Date//Date"])
        for hour in range(1, 25):
            text = row[f"H{hour:02d}//H{hour:02d}"].strip()
            try:
                value = float(text)
            except ValueError:
                invalid_count += 1
                continue
            if value == -999:
                invalid_count += 1
                continue
            if not math.isfinite(value) or value < 0:
                invalid_count += 1
                continue
            observations.append(
                NapsPm25Observation(
                    station_id=station_id,
                    method_code=method_code,
                    city=row["City//Ville"].strip(),
                    province=province,
                    latitude=latitude,
                    longitude=longitude,
                    interval_end_utc=_utc_interval_end(
                        day,
                        hour,
                        standard_offset_hours=_standard_offset(province, longitude),
                    ),
                    value_ug_m3=value,
                )
            )
            method_counts[(station_id, method_code)] += 1
    primary_methods: dict[str, str] = {}
    for station_id in station_coordinates:
        candidates = [
            (count, method)
            for (station, method), count in method_counts.items()
            if station == station_id
        ]
        if candidates:
            primary_methods[station_id] = sorted(
                candidates,
                key=lambda item: (-item[0], item[1]),
            )[0][1]
    if choose_primary_method:
        observations = [
            item for item in observations if item.method_code == primary_methods[item.station_id]
        ]
    observations.sort(key=lambda item: (item.interval_end_utc, item.station_id))
    return observations, {
        "schema_version": 1,
        "product": "NAPS final continuous hourly PM2.5",
        "temporal_convention": "hour ending local standard time converted to UTC",
        "units": "ug m-3",
        "source_path": path.as_posix(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "observation_count": len(observations),
        "invalid_or_missing_hour_count": invalid_count,
        "station_count": len(station_coordinates),
        "primary_methods": dict(sorted(primary_methods.items())),
    }


def observations_by_station(
    observations: Iterable[NapsPm25Observation],
) -> dict[str, list[NapsPm25Observation]]:
    result: dict[str, list[NapsPm25Observation]] = defaultdict(list)
    for observation in observations:
        result[observation.station_id].append(observation)
    return dict(result)
