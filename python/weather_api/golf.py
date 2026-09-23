"""Bounded golf point assessments over ETL-owned rasters. Never fetch upstream data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weather_api.forecast import (
    PRECIPITATION_FIELDS,
    _precipitation_plan,
    nearest_region,
    timestamp,
    utc_text,
)
from weather_api.repository import CatalogueNotFoundError

HOUR = timedelta(hours=1)
RULE_VERSION = "golf-fit-v3"


class GolfLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    minTemperatureC: float = Field(8, ge=-30, le=50)
    maxTemperatureC: float = Field(30, ge=-30, le=50)
    maxWindKmh: float = Field(25, ge=0, le=150)
    maxRainMm: float = Field(1, ge=0, le=100)
    maxPopPercent: float = Field(40, ge=0, le=100)

    @model_validator(mode="after")
    def ordered(self):
        if self.minTemperatureC >= self.maxTemperatureC:
            raise ValueError("Minimum temperature must be below maximum temperature")
        return self


def playing_windows(first: date, tee: time, zone: ZoneInfo, days: int) -> list[dict]:
    result = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        local = datetime.combine(day, tee, tzinfo=zone)
        start = local.astimezone(UTC)
        valid = start.astimezone(zone).replace(tzinfo=None) == local.replace(tzinfo=None)
        result.append({"date": day.isoformat(), "tee": start, "valid": valid})
    return result


def scalar_range(rows, key, start, end):
    """Linear temporal interpolation only between present native steps <=3 h apart."""
    points = sorted((timestamp(r["time"]), r.get(key)) for r in rows)
    values = []
    covered = start
    for (left, a), (right, b) in zip(points, points[1:], strict=False):
        if a is None or b is None or right <= start or left >= end or right - left > 3 * HOUR:
            continue
        lo, hi = max(start, left), min(end, right)
        if lo > covered:
            return None
        for at in (lo, hi):
            values.append(a + (b - a) * (at - left) / (right - left))
        covered = max(covered, hi)
    if covered < end or not values:
        return None
    return [round(min(values), 2), round(max(values), 2)]


def rain_bounds(rows, start, end):
    """Never prorate rain: bracket an unaligned window with complete native totals."""
    amounts = {
        (timestamp(r["start"]), timestamp(r["end"]), r["field"]): r["mm"]
        for r in rows
        if r["mm"] is not None
    }
    lefts = sorted({a for a, _, _ in amounts if start - 3 * HOUR < a <= start}, reverse=True)
    rights = sorted({b for _, b, _ in amounts if end <= b < end + 3 * HOUR})
    for left in lefts:
        for right in rights:
            plan = _precipitation_plan(left, right, set(amounts))
            if plan:
                upper = sum(amounts[i] for i in plan if i[0] < end and i[1] > start)
                lower = sum(amounts[i] for i in plan if i[0] >= start and i[1] <= end)
                return {
                    "minimumMm": round(lower, 2),
                    "maximumMm": round(upper, 2),
                    "coverStart": utc_text(left),
                    "coverEnd": utc_text(right),
                }
    return None


def regional_context(regions, longitude, latitude):
    match = nearest_region(regions, longitude, latitude)
    # This is explicitly nearby context, not a point PoP or a polygon assignment.
    if not match or match["distanceKm"] > 50:
        return None
    region = match["region"]
    return {
        "name": region.get("locality") or region["name"],
        "distanceKm": match["distanceKm"],
        "issuedAt": region["issuedAt"],
        "stale": region["stale"],
        "periods": region["periods"],
    }


def period_pop(context, start, end):
    if not context or context["stale"]:
        return None
    periods = sorted(
        (
            p
            for p in context["periods"]
            if timestamp(p["start"]) < end and timestamp(p["end"]) > start
        ),
        key=lambda p: p["start"],
    )
    covered, values = start, []
    for period in periods:
        a, b, value = timestamp(period["start"]), timestamp(period["end"]), period.get("popPercent")
        if a > covered or value is None or not math.isfinite(value) or not 0 <= value <= 100:
            return None
        values.append(value)
        covered = max(covered, b)
    return max(values) if values and covered >= end else None


def segment(rows, rain, context, name, start, end, limits):
    temperature = scalar_range(rows, "temperatureC", start, end)
    wind = scalar_range(rows, "windKmh", start, end)
    gust = scalar_range(rows, "gustKmh", start, end)
    amount = rain_bounds(rain, start, end)
    pop = period_pop(context, start, end)
    checks = []

    def check(field, label, value, limit, scale):
        known = value is not None
        state = "unknown" if not known else "within" if value <= limit else "outside"
        # 50 is the user's maximum tolerance, not a probability or a safety threshold.
        fit = None if not known else max(0, min(100, 50 + 50 * (limit - value) / scale))
        if known and field != "temperature" and value == limit == 0:
            fit = 100
        checks.append({"field": field, "label": label, "state": state, "fit": fit})

    if temperature:
        margin = min(
            temperature[0] - limits.minTemperatureC, limits.maxTemperatureC - temperature[1]
        )
        check("temperature", "Temperature", -margin, 0, 5)
    else:
        check("temperature", "Temperature", None, 0, 5)
    check(
        "wind",
        "Sustained wind",
        wind[1] if wind else None,
        limits.maxWindKmh,
        max(10, limits.maxWindKmh),
    )
    rain_uncertain = amount and amount["minimumMm"] <= limits.maxRainMm < amount["maximumMm"]
    check(
        "rain",
        "Precipitation amount",
        None if rain_uncertain or not amount else amount["maximumMm"],
        limits.maxRainMm,
        max(2, limits.maxRainMm),
    )
    check(
        "pop", "Regional rain probability", pop, limits.maxPopPercent, max(20, limits.maxPopPercent)
    )
    if pop is None:
        # A bulletin need not publish a numeric probability. This is an optional
        # criterion, not a failure of the point-model weather assessment.
        checks[-1]["state"] = "not_provided"
    return {
        "name": name,
        "start": utc_text(start),
        "end": utc_text(end),
        "temperatureRangeC": temperature,
        "maxWindKmh": wind[1] if wind else None,
        "maxGustKmh": gust[1] if gust else None,
        "rain": amount,
        "popPercent": pop,
        "checks": checks,
        "rainTimingUncertain": bool(rain_uncertain),
    }


def briefing_detail(parts):
    """A short, grounded phrasing anchor for local-model wording, not new weather."""
    clauses = []
    labels = {
        "temperature": "temperature",
        "wind": "sustained wind",
        "rain": "precipitation amount",
        "pop": "regional precipitation probability",
    }
    for state in ("outside", "unknown"):
        flagged = [
            (part, check)
            for part in parts
            for check in part["checks"]
            if check["state"] == state and not (state == "unknown" and check["field"] == "pop")
        ]
        if not flagged:
            continue
        # Prioritize during-round limitations, then lead-in and buffer.
        field = next(
            (c["field"] for p, c in flagged if p["name"] == "Round"), flagged[0][1]["field"]
        )
        phases = [p["name"] for p, c in flagged if c["field"] == field]
        when = (
            "before, during and after the round"
            if len(phases) == 3
            else " and ".join(
                {
                    "Before": "before the round",
                    "Round": "during the round",
                    "After": "after the round",
                }[p]
                for p in phases
            )
        )
        condition = (
            "falls outside your limits" if state == "outside" else "cannot be fully assessed"
        )
        clauses.append(f"{labels[field]} {condition} {when}")
    if not clauses:
        if any(p["rain"] and p["rain"]["maximumMm"] > 0 for p in parts):
            return (
                "Forecast precipitation stays within your chosen amount, with temperature "
                "and wind also within your preferences before, during and after the round."
            )
        return (
            "The point model forecasts no precipitation before, during or after the round, "
            "with temperature and wind within your preferences."
        )
    return "; ".join(clauses).capitalize() + "."


def assess_day(window, rows, rain, context, limits, run, now):
    start = window["tee"]
    ranges = [
        ("Before", start - 2 * HOUR, start),
        ("Round", start, start + 4 * HOUR),
        ("After", start + 4 * HOUR, start + 5 * HOUR),
    ]
    parts = [segment(rows, rain, context, name, a, b, limits) for name, a, b in ranges]
    missing = [
        f"{p['name']}: {c['label']}"
        for p in parts
        for c in p["checks"]
        if c["state"] == "unknown" and c["field"] != "pop"
    ]
    outside = [
        f"{p['name']}: {c['label']}" for p in parts for c in p["checks"] if c["state"] == "outside"
    ]
    stale = run is None or now - run > timedelta(hours=24)
    state = (
        "invalid_time"
        if not window["valid"]
        else "started"
        if start <= now
        else "stale"
        if stale
        else "incomplete"
        if missing
        else "outside"
        if outside
        else "within"
    )
    score = None
    if state in {"within", "outside"}:
        # Unpublished PoP is optional, not converted to zero or considered a pass.
        # Known PoP still contributes and can fail the saved probability limit.
        fits = [min(c["fit"] for c in p["checks"] if c["fit"] is not None) for p in parts]
        score = round(0.15 * fits[0] + 0.7 * fits[1] + 0.15 * fits[2])
        if any(c["state"] == "outside" for c in parts[1]["checks"]):
            score = min(49, score)
    reasons = []
    if state == "invalid_time":
        reasons.append("This tee time does not exist on this date in the selected time zone.")
    elif state == "started":
        reasons.append("This tee time has passed; choose a future round.")
    elif state == "stale":
        reasons.append("A recent point-model run is unavailable; no score is shown.")
    if outside:
        reasons.append("Beyond your limits: " + "; ".join(outside) + ".")
    if missing:
        reasons.append("Not enough data to check: " + "; ".join(missing) + ".")
    if state == "within":
        reasons.append(
            "The available forecasts fit your limits before, during and after the round."
        )
    if any(p["rainTimingUncertain"] for p in parts):
        reasons.append("Native precipitation intervals cannot resolve your exact playing window.")
    relevant_periods = [
        p
        for p in (context or {}).get("periods", [])
        if timestamp(p["start"]) < ranges[-1][2] and timestamp(p["end"]) > ranges[0][1]
    ]
    day_rows = [
        r for r in rows if ranges[0][1] - 3 * HOUR < timestamp(r["time"]) < ranges[-1][2] + 3 * HOUR
    ]
    day_rain = [
        r
        for r in rain
        if timestamp(r["start"]) < ranges[-1][2] and timestamp(r["end"]) > ranges[0][1]
    ]
    result = {
        "date": window["date"],
        "teeTime": utc_text(start),
        "endTime": utc_text(start + 4 * HOUR),
        "state": state,
        "score": score,
        "scoreCoverage": "none" if score is None else "complete",
        "probabilityNote": None,
        "segments": parts,
        "reasons": reasons,
        "briefingDetail": briefing_detail(parts),
        "modelRows": day_rows,
        "precipitationIntervals": day_rain,
        "regionalPeriods": relevant_periods,
    }
    result["contentID"] = hashlib.sha256(
        json.dumps(
            [RULE_VERSION, result, limits.model_dump(), utc_text(run) if run else None],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return result


async def collect_point(repository, longitude, latitude, windows, now, sample):
    """Read one explicit cycle; never splice model runs or collect for a client."""
    runs = await repository.list_runs("gdps", 4, field="air_temperature_2m")
    eligible = [r for r in runs if r["run_time"] <= now]
    complete = [
        r for r in eligible if r.get("status") == "complete" and now - r["run_time"] <= 24 * HOUR
    ]
    # While the new cycle is still arriving, retain a recent complete cycle so
    # later golf days do not disappear simply because ingestion is in progress.
    run = (complete or eligible)[0]["run_time"] if eligible else None
    if run is None:
        return {"runTime": None, "rows": [], "rain": []}
    semaphore = asyncio.Semaphore(4)
    bands = [(w["tee"] - 5 * HOUR, w["tee"] + 8 * HOUR) for w in windows]

    async def field_rows(field, unit, scale, duration=None):
        frames = await repository.list_times("gdps", run, field=field)
        selected = []
        for f in frames:
            valid = f["valid_time"]
            if valid < run or not any(a <= valid <= b for a, b in bands):
                continue
            if duration is not None:
                # GDPS product-time records are shared across fields and have
                # generic instantaneous metadata. The registered accumulation
                # field and validated lead define the interval, as in the
                # regional precipitation endpoint, not those generic columns.
                hours, max_lead = PRECIPITATION_FIELDS[field]
                lead = f.get("forecast_hour")
                if (
                    lead is None
                    or not hours <= lead <= max_lead
                    or lead % hours != 0
                    or valid != run + lead * HOUR
                ):
                    continue
            selected.append(f)
        # Cap every field independently even if a catalogue unexpectedly expands.
        selected = sorted(selected, key=lambda f: f["valid_time"])[:110]

        async def read(frame):
            value = None
            try:
                async with semaphore:
                    item = await sample(
                        repository,
                        product="gdps",
                        domain="global",
                        run_time=run,
                        valid_time=frame["valid_time"],
                        field=field,
                        longitude=longitude,
                        latitude=latitude,
                    )
                if not item.nodata and item.value is not None and item.unit == unit:
                    candidate = item.value * scale
                    if math.isfinite(candidate) and (
                        field == "air_temperature_2m" or candidate >= 0
                    ):
                        value = round(candidate, 2)
            except (CatalogueNotFoundError, FileNotFoundError, OSError):
                pass
            return frame["valid_time"], value

        return await asyncio.gather(*(read(f) for f in selected))

    tasks = [
        field_rows("air_temperature_2m", "degC", 1),
        field_rows("wind_speed_10m", "m/s", 3.6),
        field_rows("wind_gust_10m", "m/s", 3.6),
        field_rows("total_precipitation_1h", "mm", 1, HOUR),
        field_rows("total_precipitation_3h", "mm", 1, 3 * HOUR),
    ]
    temperature, wind, gust, rain1, rain3 = await asyncio.gather(*tasks)
    rows = {}
    for key, data in [("temperatureC", temperature), ("windKmh", wind), ("gustKmh", gust)]:
        for valid, value in data:
            rows.setdefault(
                valid,
                {"time": utc_text(valid), "temperatureC": None, "windKmh": None, "gustKmh": None},
            )[key] = value
    rain = [
        {
            "start": utc_text(valid - duration * HOUR),
            "end": utc_text(valid),
            "field": f"total_precipitation_{duration}h",
            "mm": value,
        }
        for duration, data in [(1, rain1), (3, rain3)]
        for valid, value in data
    ]
    return {"runTime": utc_text(run), "rows": [rows[t] for t in sorted(rows)], "rain": rain}


def golf_outlook(point, regions, longitude, latitude, zone, windows, limits, now):
    context = regional_context(regions, longitude, latitude)
    run = timestamp(point["runTime"]) if point["runTime"] else None
    return {
        "schemaVersion": 1,
        "generatedAt": utc_text(now),
        "ruleVersion": RULE_VERSION,
        "latitude": latitude,
        "longitude": longitude,
        "timeZone": zone.key,
        "source": "ECCC GDPS",
        "runTime": point["runTime"],
        "limits": limits.model_dump(),
        "regionalContext": {k: v for k, v in context.items() if k != "periods"}
        if context
        else None,
        "method": (
            "Model-grid point sample; linear temperature/wind interpolation across native steps "
            "of at most 3 hours. Precipitation is liquid equivalent, bounded without prorating. "
            "PoP is nearby regional context, not a point or hourly probability."
        ),
        "scoreMeaning": (
            "Weather-fit index, not a probability or safety guarantee. "
            "50 is the tolerance boundary. Before/round/after weights are 15/70/15%; "
            "a round limit breach caps the score below 50. "
            "Missing temperature, wind or precipitation amount means no score. "
            "The rain-chance preference applies when a regional percentage is published. "
            "Otherwise the assessment uses point-model temperature, wind and precipitation "
            "amounts, with regional forecasts as context."
        ),
        "days": [
            assess_day(w, point["rows"], point["rain"], context, limits, run, now) for w in windows
        ],
    }
