"""Server-owned observing forecasts over collected grids; no provider requests.

Initial release is deliberately a total-cloud preview. Layered clouds, seeing
and transparency require independently verified numerical feeds.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import astronomy as astro
from pydantic import BaseModel, ConfigDict, Field
from tzfpy import get_tz

from weather_api.forecast import PRECIPITATION_FIELDS, timestamp, utc_text
from weather_api.golf import HOUR, rain_bounds
from weather_api.repository import CatalogueNotFoundError

RULE_VERSION = "cloud-darkness-preview-v1"
FIELDS = {
    "cloudPercent": ("total_cloud_cover", "%", "percent", 1, 0, 100),
    "temperatureC": ("air_temperature_2m", "°C", "degC", 1, -100, 70),
    "humidityPercent": ("relative_humidity_2m", "%", "percent", 1, 0, 100),
    "windKmh": ("wind_speed_10m", "km/h", "m/s", 3.6, 0, 500),
    "gustKmh": ("wind_gust_10m", "km/h", "m/s", 3.6, 0, 500),
}
LIMITATIONS = [
    "Total-cloud preview: low, middle and high cloud layers are not yet available.",
    "Seeing and transparency are not assessed; clear skies do not guarantee steady images.",
    "Cloud percentages are sky fractions, not a probability of observing success.",
    "Dew risk is a surface-weather heuristic, not a prediction of telescope temperature.",
]


class ObservingCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    maxCloudPercent: float = Field(30, ge=0, le=100)
    maxWindKmh: float = Field(25, ge=0, le=150)
    maxRainMm: float = Field(0, ge=0, le=20)
    minimumMinutes: int = Field(60, ge=30, le=240)


def site_zone(longitude: float, latitude: float) -> ZoneInfo:
    # Coordinates, never a nearby regional forecast centre, determine the zone.
    return ZoneInfo(get_tz(longitude, latitude) or "UTC")


def engine_time(at: datetime) -> astro.Time:
    return astro.Time(utc_text(at))


def altitude(body: astro.Body, observer: astro.Observer, at: datetime) -> float:
    t = engine_time(at)
    equatorial = astro.Equator(body, t, observer, True, True)
    return astro.Horizon(
        t, observer, equatorial.ra, equatorial.dec, astro.Refraction.Airless
    ).altitude


def sky(observer: astro.Observer, at: datetime) -> dict:
    t = engine_time(at)
    phase = astro.MoonPhase(t)
    phase_name = (
        "Waxing crescent"
        if phase < 90
        else "Waxing gibbous"
        if phase < 180
        else "Waning gibbous"
        if phase < 270
        else "Waning crescent"
    )
    for angle, name in [
        (0, "Near new moon"),
        (90, "Near first quarter"),
        (180, "Near full moon"),
        (270, "Near last quarter"),
    ]:
        if abs((phase - angle + 180) % 360 - 180) < 2:
            phase_name = name
            break
    return {
        "sunAltitudeDegrees": round(altitude(astro.Body.Sun, observer, at), 2),
        "moonAltitudeDegrees": round(altitude(astro.Body.Moon, observer, at), 2),
        "moonIlluminatedPercent": round(
            100 * astro.Illumination(astro.Body.Moon, t).phase_fraction, 1
        ),
        "moonPhaseDegrees": round(phase, 1),
        "moonPhaseName": phase_name,
    }


def event(observer, body, start, end, direction, level=None):
    days = (end - start).total_seconds() / 86400
    if level is None:
        result = astro.SearchRiseSet(body, observer, direction, engine_time(start), days)
    else:
        result = astro.SearchAltitude(body, observer, direction, engine_time(start), days, level)
    if result is None:
        return None
    at = result.Utc().replace(tzinfo=UTC)
    return at if start <= at < end else None


def dark_intervals(observer, start, end, level=-18, moonless=False):
    """Exact altitude transitions, including polar days/nights and missing events."""
    boundaries = {start, end}
    for body, threshold in [(astro.Body.Sun, level)] + ([(astro.Body.Moon, 0)] if moonless else []):
        for direction in (astro.Direction.Rise, astro.Direction.Set):
            at = start
            # Noon-to-noon spans at most 25 hours at DST; allow two same-direction events.
            for _ in range(3):
                found = event(observer, body, at, end, direction, threshold)
                if found is None:
                    break
                boundaries.add(found)
                at = found + timedelta(seconds=2)
    result = []
    ordered = sorted(boundaries)
    for a, b in zip(ordered, ordered[1:], strict=False):
        middle = a + (b - a) / 2
        if altitude(astro.Body.Sun, observer, middle) > level:
            continue
        if moonless and altitude(astro.Body.Moon, observer, middle) >= 0:
            continue
        if result and result[-1][1] == a:
            result[-1] = (result[-1][0], b)
        else:
            result.append((a, b))
    return result


async def collect_weather(repository, sample, longitude, latitude, product, start, end, now):
    runs = await repository.list_runs(product, 6, field="total_cloud_cover")
    eligible = [r for r in runs if r["run_time"] <= now]
    recent_complete = [
        r for r in eligible if r.get("status") == "complete" and now - r["run_time"] <= 24 * HOUR
    ]
    selected = recent_complete or eligible
    run = selected[0]["run_time"] if selected else None
    if run is None:
        return {"runTime": None, "rows": [], "rain": [], "sample": None}
    semaphore = asyncio.Semaphore(4)
    locations = {}

    async def field_rows(key, field, unit, scale, lower, upper, duration=None):
        frames = await repository.list_times(product, run, field=field)
        chosen = []
        for frame in sorted(frames, key=lambda f: f["valid_time"]):
            valid = frame["valid_time"]
            if not max(run, start - 3 * HOUR) <= valid <= end + 3 * HOUR:
                continue
            if duration:
                lead = frame.get("forecast_hour")
                hours, maximum = PRECIPITATION_FIELDS[field]
                if lead is None or not hours <= lead <= maximum or lead % hours:
                    continue
                if valid != run + lead * HOUR:
                    continue
            chosen.append(frame)

        async def read(frame):
            value = None
            try:
                async with semaphore:
                    item = await sample(
                        repository,
                        product=product,
                        domain={"gdps": "global", "rdps": "north_america", "hrdps": "continental"}[
                            product
                        ],
                        run_time=run,
                        valid_time=frame["valid_time"],
                        field=field,
                        longitude=longitude,
                        latitude=latitude,
                    )
                candidate = item.get("value")
                if candidate is not None and item["unit"] == unit:
                    candidate *= scale
                    if math.isfinite(candidate) and lower <= candidate <= upper:
                        value = round(candidate, 2)
                        locations[key] = item.get("sample")
            except (CatalogueNotFoundError, FileNotFoundError, OSError):
                pass
            return frame["valid_time"], value

        return key, await asyncio.gather(*(read(f) for f in chosen[:190]))

    specifications = [
        (key, field, unit, scale, lower, upper, None)
        for key, (field, _, unit, scale, lower, upper) in FIELDS.items()
    ] + [
        (f"rain{hours}", f"total_precipitation_{hours}h", "mm", 1, 0, 2000, hours)
        for hours in (1, 3)
    ]
    if product != "gdps":
        specifications += [
            (key, field, "m/s", 3.6, -500, 500, None)
            for key, field in [("windU", "wind_u_10m"), ("windV", "wind_v_10m")]
        ]
    data = await asyncio.gather(*(field_rows(*spec) for spec in specifications))
    rows, rain = {}, []
    for key, values in data:
        for valid, value in values:
            if key.startswith("rain"):
                duration = int(key[4:])
                rain.append(
                    {
                        "start": utc_text(valid - duration * HOUR),
                        "end": utc_text(valid),
                        "field": f"total_precipitation_{duration}h",
                        "mm": value,
                    }
                )
            else:
                rows.setdefault(valid, {"time": utc_text(valid), **dict.fromkeys(FIELDS)})[key] = (
                    value
                )
    for row in rows.values():
        u, v = row.pop("windU", None), row.pop("windV", None)
        if row["windKmh"] is None and u is not None and v is not None:
            row["windKmh"] = round(math.hypot(u, v), 2)
    return {
        "runTime": utc_text(run),
        "rows": [rows[t] for t in sorted(rows)],
        "rain": rain,
        "sample": locations.get("cloudPercent"),
        "fieldSamples": locations,
    }


def dew_point(temperature, humidity):
    if temperature is None or humidity is None or humidity <= 0:
        return None
    # Magnus approximation for surface dew point; intentionally labelled heuristic.
    gamma = math.log(humidity / 100) + 17.625 * temperature / (243.04 + temperature)
    return round(243.04 * gamma / (17.625 - gamma), 2)


def qualify(rows, rain, darkness, start, end, criteria, fresh):
    windows, counts = [], {"cloud": 0, "wind": 0, "precipitation": 0, "missing": 0}
    covered_seconds = 0.0
    wanted_seconds = sum(max(0, (min(b, end) - max(a, start)).total_seconds()) for a, b in darkness)
    if not fresh:
        return [], "insufficient_data", "A recent cloud-model run is unavailable."
    for left, right in zip(rows, rows[1:], strict=False):
        a, b = timestamp(left["time"]), timestamp(right["time"])
        if not 0 < (b - a).total_seconds() <= 10800:
            continue
        if b <= start or a >= end:
            continue
        dark_seconds = sum(
            max(0, (min(b, hi, end) - max(a, lo, start)).total_seconds()) for lo, hi in darkness
        )
        if not dark_seconds:
            continue
        required = [left.get(k) for k in ("cloudPercent", "windKmh")] + [
            right.get(k) for k in ("cloudPercent", "windKmh")
        ]
        amount = rain_bounds(rain, a, b)
        reason = None
        if any(v is None for v in required) or amount is None:
            reason = "missing"
        elif max(left["cloudPercent"], right["cloudPercent"]) > criteria.maxCloudPercent:
            reason = "cloud"
        elif max(left["windKmh"], right["windKmh"]) > criteria.maxWindKmh:
            reason = "wind"
        elif amount["maximumMm"] > criteria.maxRainMm:
            reason = "precipitation"
        if reason != "missing":
            covered_seconds += dark_seconds
        if reason:
            counts[reason] += 1
            continue
        for dark_start, dark_end in darkness:
            lo, hi = max(a, dark_start, start), min(b, dark_end, end)
            if lo >= hi:
                continue
            if windows and windows[-1][1] == lo:
                windows[-1] = (windows[-1][0], hi)
            else:
                windows.append((lo, hi))
    windows = [
        (a, b) for a, b in windows if (b - a).total_seconds() >= criteria.minimumMinutes * 60
    ]
    if windows:
        return windows, "window", "Cloud, wind and precipitation meet your limits during darkness."
    if not darkness:
        return [], "no_window", "No qualifying darkness for this observing mode."
    if not rows or counts["missing"] or covered_seconds < wanted_seconds - 1:
        return (
            [],
            "insufficient_data",
            "Weather coverage is incomplete; missing values are not clear skies.",
        )
    factors = [k for k in ("cloud", "wind", "precipitation") if counts[k]]
    return (
        [],
        "no_window",
        "No qualifying window: "
        + (", ".join(factors) or "insufficient duration or coverage")
        + ".",
    )


def build_forecast(weather, longitude, latitude, product, now, nights, mode, criteria):
    zone = site_zone(longitude, latitude)
    observer = astro.Observer(latitude, longitude, 0)
    first = now.astimezone(zone).date()
    # Before noon, keep the observing night that began yesterday together.
    if now.astimezone(zone).hour < 12:
        first -= timedelta(days=1)
    run = timestamp(weather["runTime"]) if weather["runTime"] else None
    fresh = run is not None and timedelta(0) <= now - run <= 24 * HOUR
    frames = []
    for row in weather["rows"]:
        at = timestamp(row["time"])
        dew = dew_point(row.get("temperatureC"), row.get("humidityPercent"))
        amount = next(
            (
                r
                for r in weather["rain"]
                if r["end"] == row["time"]
                and r["mm"] is not None
                and r["field"] == "total_precipitation_1h"
            ),
            None,
        )
        if amount is None:
            amount = next(
                (r for r in weather["rain"] if r["end"] == row["time"] and r["mm"] is not None),
                None,
            )
        frames.append(
            {
                **row,
                **sky(observer, at),
                "dewPointC": dew,
                "dewRisk": None if dew is None else row["temperatureC"] - dew <= 2,
                "rainMm": amount["mm"] if amount else None,
                "rainStart": amount["start"] if amount else None,
            }
        )
    sessions = []
    for offset in range(nights):
        day = first + timedelta(days=offset)
        start = datetime.combine(day, time(12), zone).astimezone(UTC)
        end = datetime.combine(day + timedelta(days=1), time(12), zone).astimezone(UTC)
        dark = dark_intervals(observer, start, end)
        moonless = dark_intervals(observer, start, end, moonless=True)
        observing = moonless if mode == "deep_sky" else dark_intervals(observer, start, end, -6)
        windows, state, summary = qualify(
            weather["rows"], weather["rain"], observing, max(start, now), end, criteria, fresh
        )
        events = {}
        for label, body, direction, level in [
            ("sunset", astro.Body.Sun, astro.Direction.Set, None),
            ("sunrise", astro.Body.Sun, astro.Direction.Rise, None),
            ("civilDusk", astro.Body.Sun, astro.Direction.Set, -6),
            ("civilDawn", astro.Body.Sun, astro.Direction.Rise, -6),
            ("nauticalDusk", astro.Body.Sun, astro.Direction.Set, -12),
            ("nauticalDawn", astro.Body.Sun, astro.Direction.Rise, -12),
            ("astronomicalDusk", astro.Body.Sun, astro.Direction.Set, -18),
            ("astronomicalDawn", astro.Body.Sun, astro.Direction.Rise, -18),
            ("moonrise", astro.Body.Moon, astro.Direction.Rise, None),
            ("moonset", astro.Body.Moon, astro.Direction.Set, None),
        ]:
            found = event(observer, body, start, end, direction, level)
            events[label] = utc_text(found) if found else None

        def intervals(values):
            return [
                {
                    "start": utc_text(a),
                    "end": utc_text(b),
                    "minutes": round((b - a).total_seconds() / 60),
                }
                for a, b in values
            ]

        sessions.append(
            {
                "date": day.isoformat(),
                "start": utc_text(start),
                "end": utc_text(end),
                "events": events,
                "darkness": intervals(dark),
                "moonlessDarkness": intervals(moonless),
                "windows": intervals(windows),
                "state": state,
                "summary": summary,
                **sky(observer, start + (end - start) / 2),
            }
        )
    return {
        "schemaVersion": 1,
        "generatedAt": utc_text(now),
        "preview": True,
        "latitude": latitude,
        "longitude": longitude,
        "timeZone": zone.key,
        "product": product,
        "source": f"ECCC {product.upper()}",
        "runTime": weather["runTime"],
        "stale": not fresh,
        "sample": weather.get("sample"),
        "fieldSamples": weather.get("fieldSamples", {}),
        "mode": mode,
        "criteria": criteria.model_dump(),
        "ruleVersion": RULE_VERSION,
        "ephemerisVersion": "astronomy-engine-2.1.19",
        "limitations": LIMITATIONS,
        "method": "Nearest native raster cell; no invented hourly steps or model/run splicing. "
        "Windows use the worse adjacent cloud/wind samples (gaps <=3h), complete "
        "native rain totals, and exact Sun/Moon altitude transitions. "
        "Deep-sky: Sun below -18° and Moon below geometric horizon. "
        "Lunar/planetary: Sun below -6°; moonlight is allowed. "
        "Observer at sea level, unobstructed horizon; standard refraction for rise/set, "
        "airless altitude for twilight and darkness. Local terrain is not modelled.",
        "unavailableFields": [
            "lowCloudPercent",
            "middleCloudPercent",
            "highCloudPercent",
            "seeing",
            "transparency",
            "visibility",
        ],
        "frames": frames,
        "nights": sessions,
    }
