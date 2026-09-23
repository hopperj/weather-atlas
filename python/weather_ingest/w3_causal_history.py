"""Pure operators for physically time-causal W3 source histories."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return result.astimezone(UTC)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def haversine_km(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    first_latitude_rad, second_latitude_rad = map(math.radians, (first_latitude, second_latitude))
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    value = (
        math.sin(latitude_delta / 2.0) ** 2
        + math.cos(first_latitude_rad)
        * math.cos(second_latitude_rad)
        * math.sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * 6371.0088 * math.asin(math.sqrt(value))


def row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def finite_state(row: dict[str, str]) -> bool:
    try:
        return all(math.isfinite(float(row[field])) for field in ("ffmc", "dmc", "dc"))
    except (KeyError, ValueError):
        return False


def source_records(
    rows: Iterable[dict[str, str]],
    *,
    source_latitude: float,
    source_longitude: float,
    start: datetime,
    end: datetime,
    maximum_distance_km: float,
) -> list[dict[str, Any]]:
    """Select Fire M3 evidence available no later than the overpass."""

    records = []
    for row in rows:
        if row.get("country", "").strip().upper() != "C" or not finite_state(row):
            continue
        observed = datetime.strptime(row["rep_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if not start <= observed <= end:
            continue
        distance = haversine_km(
            source_latitude,
            source_longitude,
            float(row["lat"]),
            float(row["lon"]),
        )
        if distance > maximum_distance_km:
            continue
        records.append(
            {
                "observed_at": observed,
                "distance_km": distance,
                "ffmc": float(row["ffmc"]),
                "dmc": float(row["dmc"]),
                "dc": float(row["dc"]),
                "sensor": row.get("sensor", "").strip(),
                "source": row.get("source", "").strip(),
                "provider_row_sha256": row_hash(row),
            }
        )
    return sorted(
        records,
        key=lambda item: (
            item["observed_at"],
            item["distance_km"],
            item["provider_row_sha256"],
        ),
    )


def segment_boundaries(
    *,
    start: datetime,
    end: datetime,
    evidence_times: Iterable[datetime],
) -> list[datetime]:
    """Split at UTC hours and Fire M3 observation times."""

    if not start < end:
        raise ValueError("source-history interval must be positive")
    values = {start, end}
    cursor = start.replace(minute=0, second=0, microsecond=0)
    if cursor < start:
        cursor += timedelta(hours=1)
    while cursor < end:
        values.add(cursor)
        cursor += timedelta(hours=1)
    values.update(value for value in evidence_times if start < value < end)
    return sorted(values)


def latest_available_state(
    records: list[dict[str, Any]],
    at: datetime,
) -> dict[str, Any] | None:
    eligible = [record for record in records if record["observed_at"] <= at]
    if not eligible:
        return None
    latest_time = max(record["observed_at"] for record in eligible)
    latest = [record for record in eligible if record["observed_at"] == latest_time]
    return min(
        latest,
        key=lambda item: (item["distance_km"], item["provider_row_sha256"]),
    )


def ceil_utc_hour(value: datetime) -> datetime:
    floor = value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return floor if floor == value.astimezone(UTC) else floor + timedelta(hours=1)


def segment_at(
    segments: list[dict[str, Any]],
    at: datetime,
) -> dict[str, Any] | None:
    target = at.astimezone(UTC)
    return next(
        (
            segment
            for segment in segments
            if parse_utc(segment["start_utc"]) <= target < parse_utc(segment["end_utc"])
        ),
        None,
    )


def released_area_between(
    segments: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    curve: str = "central",
) -> float:
    """Integrate an already-frozen piecewise-uniform released-area history."""

    if end < start:
        raise ValueError("released-area interval is reversed")
    total = 0.0
    for segment in segments:
        segment_start = parse_utc(segment["start_utc"])
        segment_end = parse_utc(segment["end_utc"])
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        if overlap_end <= overlap_start:
            continue
        fraction = (overlap_end - overlap_start).total_seconds() / (
            segment_end - segment_start
        ).total_seconds()
        total += float(segment["released_area_ha"][curve]) * fraction
    return total


def uniform_area_for_interval(
    daily_increment_ha: dict[str, float],
    start: datetime,
    end: datetime,
) -> float:
    if start.date() != (end - timedelta(microseconds=1)).date():
        raise ValueError("area interval must not cross a UTC date boundary")
    value = float(daily_increment_ha.get(start.date().isoformat(), 0.0))
    return value * (end - start).total_seconds() / 86_400.0


def area_partition(
    daily_increment_ha: dict[str, float],
    *,
    history_start: datetime,
    overpass: datetime,
) -> dict[str, float]:
    before_window = 0.0
    within_window = 0.0
    after_overpass = 0.0
    for day_text, area_value in daily_increment_ha.items():
        day = date.fromisoformat(day_text)
        day_start = datetime.combine(day, time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        area = float(area_value)
        before_seconds = max(
            0.0,
            (min(day_end, history_start) - day_start).total_seconds(),
        )
        within_seconds = max(
            0.0,
            (min(day_end, overpass) - max(day_start, history_start)).total_seconds(),
        )
        after_seconds = max(
            0.0,
            (day_end - max(day_start, overpass)).total_seconds(),
        )
        before_window += area * before_seconds / 86_400.0
        within_window += area * within_seconds / 86_400.0
        after_overpass += area * after_seconds / 86_400.0
    return {
        "before_history_window_ha": before_window,
        "within_history_window_ha": within_window,
        "after_overpass_excluded_ha": after_overpass,
    }


def verify_causality(
    *,
    overpass: datetime,
    segments: list[dict[str, Any]],
) -> dict[str, bool]:
    return {
        "all_segment_starts_before_overpass": all(
            parse_utc(segment["start_utc"]) < overpass for segment in segments
        ),
        "all_segment_ends_no_later_than_overpass": all(
            parse_utc(segment["end_utc"]) <= overpass for segment in segments
        ),
        "all_fire_state_observations_available_by_segment_start": all(
            segment.get("fire_state") is None
            or parse_utc(segment["fire_state"]["observed_at_utc"])
            <= parse_utc(segment["start_utc"])
            for segment in segments
        ),
        "all_meteorology_cycles_initialized_by_segment_start": all(
            parse_utc(segment["meteorology"]["initialization_time_utc"])
            <= parse_utc(segment["start_utc"])
            for segment in segments
        ),
        "no_post_overpass_area_released": all(
            parse_utc(segment["end_utc"]) <= overpass
            for segment in segments
            if float(segment["released_area_ha"]["central"]) > 0
        ),
    }
