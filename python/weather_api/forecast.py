"""Regional outlooks and an explicit, gap-preserving 72-hour model series."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weather_api.repository import CatalogueNotFoundError, CatalogueReader

HOUR = timedelta(hours=1)
PROVINCES = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}
FIELDS = {
    "temperatureC": ("air_temperature_2m", "degC", 1),
    "relativeHumidityPercent": ("relative_humidity_2m", "percent", 1),
    "precipitationMm": ("total_precipitation_1h", "mm", 1),
    "windKmh": ("wind_speed_10m", "m/s", 3.6),
    "gustKmh": ("wind_gust_10m", "m/s", 3.6),
}


def nearest_region(regions: list[dict], longitude: float, latitude: float) -> dict | None:
    """Select a nearby representative point, without claiming a region-polygon match."""
    def distance(region):
        phi1, phi2 = math.radians(latitude), math.radians(region["latitude"])
        dphi = phi2 - phi1
        dlon = math.radians(region["longitude"] - longitude)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
        return 6371 * 2 * math.asin(math.sqrt(min(1, max(0, a))))
    if not regions:
        return None
    closest = min(regions, key=distance)
    km = distance(closest)
    if km > 200:
        return None
    return {
        "region": closest,
        "distanceKm": round(km, 1),
        "matchKind": "nearest_representative_point",
    }


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Forecast timestamp requires a timezone")
    return parsed.astimezone(UTC)


def regional_outlooks(path: Path, now: datetime) -> dict[str, Any]:
    """Use each region's own horizon; never present an expired issue as current."""
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    if not 0 < path.stat().st_size <= 64 * 1024**2:
        raise ValueError("Invalid regional snapshot size")
    snapshot = json.loads(path.read_bytes())
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("provider") != "eccc"
        or snapshot.get("product") != "citypage_weather"
        or snapshot.get("type") != "FeatureCollection"
    ):
        raise ValueError("Invalid regional snapshot contract")
    regions = []
    for feature in snapshot["features"]:
        props = feature["properties"]
        province = props["province"]
        if province not in PROVINCES:
            raise ValueError("Unknown forecast province or territory")
        lon, lat = feature["geometry"]["coordinates"]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Invalid region coordinates")
        issued = timestamp(props["issued_at"])
        periods = []
        for period in props["periods"]:
            start, end = timestamp(period["valid_start"]), timestamp(period["valid_end"])
            if end <= now or start >= now + timedelta(days=7):
                continue
            if start >= end:
                raise ValueError("Invalid regional period")
            periods.append(
                {
                    "name": period["period"],
                    "start": utc_text(start),
                    "end": utc_text(end),
                    "temperatureC": period.get("temperature_c"),
                    "temperatureClass": period.get("temperature_class"),
                    "relativeHumidityPercent": period.get("relative_humidity_percent"),
                    "popPercent": period.get("pop_percent"),
                    "precipitationAmount": period.get("precipitation_amount"),
                    "condition": period.get("condition", ""),
                }
            )
        regions.append(
            {
                "id": props["area_id"],
                "name": props["name"],
                "locality": props.get("locality", props["name"]),
                "briefing": props.get("briefing"),
                "province": province,
                "provinceName": PROVINCES[province],
                "latitude": lat,
                "longitude": lon,
                "issuedAt": utc_text(issued),
                "stale": now - issued > timedelta(hours=24) or not periods,
                "periods": sorted(periods, key=lambda p: p["start"]),
            }
        )
    return {
        "generatedAt": snapshot["generated_at"],
        "timeZone": "America/Halifax",
        "regions": sorted(
            regions,
            key=lambda region: (
                region["province"] != "NS",
                region["provinceName"],
                region["name"],
            ),
        ),
    }


async def hourly_outlook(
    repository: CatalogueReader,
    region: dict[str, Any],
    now: datetime,
    sample: Callable[..., Awaitable[Any]],
) -> dict[str, Any]:
    """Use the newest available GDPS temperature run for each hour.

    Companion fields must come from that exact run/time. Missing hours and
    fields remain null; 3-hourly products and regional POP are never interpolated.
    """
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    times = [start + i * HOUR for i in range(72)]
    frames = await repository.list_timeline(
        "gdps",
        "global",
        "air_temperature_2m",
        start,
        times[-1],
        72,
    )
    by_time: dict[datetime, dict[str, Any]] = {}
    for frame in frames:
        valid, run = frame["valid_time"], frame["run_time"]
        lead = frame.get("forecast_hour")
        if valid not in times or run > now or run > valid or lead is None or not 0 <= lead <= 84:
            continue
        if valid not in by_time or run > by_time[valid]["run_time"]:
            by_time[valid] = frame
    semaphore = asyncio.Semaphore(4)

    async def hour(valid: datetime) -> dict[str, Any]:
        row: dict[str, Any] = {
            "time": utc_text(valid),
            "runTime": None,
            "precipitationStart": utc_text(valid - HOUR),
            "status": "missing",
            **dict.fromkeys(FIELDS),
        }
        frame = by_time.get(valid)
        if frame is None:
            return row
        row["runTime"] = utc_text(frame["run_time"])
        for key, (field, unit, scale) in FIELDS.items():
            try:
                async with semaphore:
                    value = await sample(
                        repository,
                        product="gdps",
                        domain="global",
                        run_time=frame["run_time"],
                        valid_time=valid,
                        field=field,
                        longitude=region["longitude"],
                        latitude=region["latitude"],
                    )
            except (CatalogueNotFoundError, FileNotFoundError, OSError):
                continue
            if value.nodata or value.value is None or value.unit != unit:
                continue
            number = value.value * scale
            if not math.isfinite(number):
                continue
            if key == "relativeHumidityPercent" and not 0 <= number <= 100:
                continue
            if key in {"precipitationMm", "windKmh", "gustKmh"} and number < 0:
                continue
            row[key] = round(number, 2)
        populated = sum(row[key] is not None for key in FIELDS)
        row["status"] = (
            "complete" if populated == len(FIELDS) else ("partial" if populated else "missing")
        )
        return row

    hours = await asyncio.gather(*(hour(valid) for valid in times))
    return {
        "regionId": region["id"],
        "source": "ECCC GDPS",
        "generatedAt": utc_text(now),
        "start": utc_text(start),
        "end": utc_text(start + 72 * HOUR),
        "availableHours": sum(row["status"] != "missing" for row in hours),
        "completeHours": sum(row["status"] == "complete" for row in hours),
        "hours": hours,
    }


PRECIPITATION_FIELDS = {
    "total_precipitation_1h": (1, 144),
    "total_precipitation_3h": (3, 168),
}


def _precipitation_plan(
    start: datetime,
    end: datetime,
    intervals: set[tuple[datetime, datetime, str]],
) -> list[tuple[datetime, datetime, str]] | None:
    """Tile the entire period exactly, preferring 1 h over overlapping 3 h.

    Work backwards so choosing a short interval cannot strand the remainder.
    Never prorate an accumulation, bridge a gap, or double-count an overlap.
    """
    paths: dict[datetime, list[tuple[datetime, datetime, str]]] = {end: []}
    for left, right, field in sorted(
        intervals, key=lambda i: (i[0], -i[1].timestamp()), reverse=True
    ):
        if start <= left < right <= end and right in paths and left not in paths:
            paths[left] = [(left, right, field), *paths[right]]
    return paths.get(start)


async def precipitation_outlook(
    repository: CatalogueReader,
    region: dict[str, Any],
    now: datetime,
    sample: Callable[..., Awaitable[Any]],
) -> dict[str, Any]:
    """Fill only absent bulletin amounts using complete single-cycle GDPS totals.

    Try the four most recent precipitation cycles from the last 48 hours. A
    period uses one initialization no later than its start, including any
    elapsed part of today's period. Incomplete or invalid samples remain null.
    """
    periods = [
        {
            "start": period["start"],
            "end": period["end"],
            "status": "official" if period["precipitationAmount"] is not None else "missing",
            "precipitationMm": None,
            "runTime": None,
            "intervals": [],
        }
        for period in region["periods"]
    ]
    response = {
        "regionId": region["id"],
        "issuedAt": region["issuedAt"],
        "source": "ECCC GDPS",
        "generatedAt": utc_text(now),
        "latitude": region["latitude"],
        "longitude": region["longitude"],
        "periods": periods,
    }
    missing = [row for row in periods if row["status"] == "missing"]
    if not missing:
        return response
    listings = await asyncio.gather(
        *(
            repository.list_runs("gdps", 4, before=now + timedelta(microseconds=1), field=field)
            for field in PRECIPITATION_FIELDS
        )
    )
    runs = sorted(
        {
            row["run_time"]
            for rows in listings
            for row in rows
            if now - 48 * HOUR <= row["run_time"] <= now
        },
        reverse=True,
    )[:4]
    semaphore = asyncio.Semaphore(4)

    async def fill_cycle(run: datetime, eligible: list[dict[str, Any]]) -> None:
        timelines = await asyncio.gather(
            *(repository.list_times("gdps", run, field=field) for field in PRECIPITATION_FIELDS)
        )
        intervals = set()
        for (field, (duration, max_lead)), frames in zip(
            PRECIPITATION_FIELDS.items(), timelines, strict=True
        ):
            for frame in frames:
                valid, lead = frame["valid_time"], frame.get("forecast_hour")
                if (
                    lead is not None
                    and duration <= lead <= max_lead
                    and lead % duration == 0
                    and valid == run + lead * HOUR
                ):
                    # Product-time rows are shared by fields. The field code,
                    # not that row's generic interval, defines the accumulation.
                    intervals.add((valid - duration * HOUR, valid, field))

        samples: dict[tuple[datetime, datetime, str], asyncio.Task[float | None]] = {}

        async def amount(interval: tuple[datetime, datetime, str]) -> float | None:
            try:
                async with semaphore:
                    value = await sample(
                        repository,
                        product="gdps",
                        domain="global",
                        run_time=run,
                        valid_time=interval[1],
                        field=interval[2],
                        longitude=region["longitude"],
                        latitude=region["latitude"],
                    )
            except (CatalogueNotFoundError, FileNotFoundError, OSError):
                return None
            if (
                value.nodata
                or value.value is None
                or value.unit != "mm"
                or not math.isfinite(value.value)
                or value.value < 0
            ):
                return None
            return float(value.value)

        async def fill(row: dict[str, Any]) -> None:
            start, end = timestamp(row["start"]), timestamp(row["end"])
            available = {i for i in intervals if start <= i[0] < i[1] <= end}
            while plan := _precipitation_plan(start, end, available):
                for interval in plan:
                    if interval not in samples:
                        samples[interval] = asyncio.create_task(amount(interval))
                values = await asyncio.gather(*(samples[interval] for interval in plan))
                invalid = {i for i, value in zip(plan, values, strict=True) if value is None}
                if invalid:
                    available -= invalid
                    continue
                row.update(
                    status="complete",
                    precipitationMm=round(math.fsum(values), 2),
                    runTime=utc_text(run),
                    intervals=[
                        {"start": utc_text(left), "end": utc_text(right), "field": field}
                        for left, right, field in plan
                    ],
                )
                return

        await asyncio.gather(*(fill(row) for row in eligible))

    for run in runs:
        eligible = [
            row
            for row in missing
            if row["status"] == "missing"
            and run <= timestamp(row["start"]) < timestamp(row["end"]) <= run + 168 * HOUR
            and timestamp(row["end"]) - timestamp(row["start"]) <= 48 * HOUR
        ]
        if eligible:
            await fill_cycle(run, eligible)
    return response
