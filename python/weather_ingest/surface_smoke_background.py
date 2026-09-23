"""Performance-blind NAPS background and smoke-enhancement operators."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from weather_ingest.naps_pm25 import NapsPm25Observation, observations_by_station


@dataclass(frozen=True, slots=True)
class SurfaceEnhancement:
    station_id: str
    interval_end_utc: datetime
    latitude: float
    longitude: float
    observed_pm25_ug_m3: float
    background_pm25_ug_m3: float
    enhancement_pm25_ug_m3: float
    background_sample_count: int
    background_statistic: str


def calculate_surface_enhancements(
    observations: Iterable[NapsPm25Observation],
    *,
    target_keys: set[tuple[str, datetime]],
    excluded_background_dates: set[date],
    excluded_background_keys: set[tuple[str, datetime]] | None = None,
    window_days: int = 14,
    minimum_background_observations: int = 7,
    statistic: str = "median",
) -> tuple[list[SurfaceEnhancement], list[dict[str, str]]]:
    """Calculate same-station/same-UTC-hour background without concentration filtering."""

    if window_days <= 0 or minimum_background_observations <= 0:
        raise ValueError("background window and minimum count must be positive")
    if statistic not in {"median", "p20"}:
        raise ValueError(f"unsupported background statistic: {statistic}")
    excluded_keys = excluded_background_keys or set()
    station_groups = observations_by_station(observations)
    lookup = {
        (item.station_id, item.interval_end_utc): item
        for items in station_groups.values()
        for item in items
    }
    enhancements: list[SurfaceEnhancement] = []
    rejections: list[dict[str, str]] = []
    for station_id, target_time in sorted(target_keys):
        target = lookup.get((station_id, target_time))
        if target is None:
            rejections.append(
                {
                    "station_id": station_id,
                    "interval_end_utc": target_time.isoformat(),
                    "reason": "missing_target_observation",
                }
            )
            continue
        values = [
            item.value_ug_m3
            for item in station_groups[station_id]
            if item.interval_end_utc.hour == target_time.hour
            and item.interval_end_utc != target_time
            and abs((item.interval_end_utc.date() - target_time.date()).days) <= window_days
            and item.interval_end_utc.date() not in excluded_background_dates
            and (station_id, item.interval_end_utc) not in excluded_keys
        ]
        if len(values) < minimum_background_observations:
            rejections.append(
                {
                    "station_id": station_id,
                    "interval_end_utc": target_time.isoformat(),
                    "reason": "insufficient_background_observations",
                    "available": str(len(values)),
                }
            )
            continue
        background = (
            float(np.median(values)) if statistic == "median" else float(np.quantile(values, 0.20))
        )
        if not math.isfinite(background):
            raise ValueError("background operator produced a non-finite value")
        enhancements.append(
            SurfaceEnhancement(
                station_id=station_id,
                interval_end_utc=target_time,
                latitude=target.latitude,
                longitude=target.longitude,
                observed_pm25_ug_m3=target.value_ug_m3,
                background_pm25_ug_m3=background,
                enhancement_pm25_ug_m3=max(
                    target.value_ug_m3 - background,
                    0.0,
                ),
                background_sample_count=len(values),
                background_statistic=statistic,
            )
        )
    return enhancements, rejections


def date_window(day: date, days: int) -> tuple[date, date]:
    return day - timedelta(days=days), day + timedelta(days=days)
