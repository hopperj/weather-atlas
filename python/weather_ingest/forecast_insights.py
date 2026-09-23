"""Server-owned immutable forecast history, comparisons and widget preparation.

No client request invokes this module's ETL entry point. Model sampling is batched
across registered region points, and every stored series belongs to one run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import rasterio
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from rasterio.warp import transform
from weather_common.db import SqlFileLoader
from weather_common.settings import Settings

from weather_ingest.storage import resolve_under

LOG = logging.getLogger(__name__)
HOUR = timedelta(hours=1)
FIELDS = {
    "air_temperature_2m": ("temperatureC", "degC", 1.0),
    "relative_humidity_2m": ("relativeHumidityPercent", "percent", 1.0),
    "total_precipitation_1h": ("precipitationMm", "mm", 1.0),
    "wind_speed_10m": ("windKmh", "m/s", 3.6),
    "wind_gust_10m": ("gustKmh", "m/s", 3.6),
}
THRESHOLDS = {"temperatureC": 2, "gustKmh": 10, "popPercent": 20, "precipitationMm": 2}
UNITS = {"temperatureC": "°C", "gustKmh": "km/h", "popPercent": "%", "precipitationMm": "mm"}
LABELS = {
    "temperatureC": "Temperature",
    "gustKmh": "Wind gusts",
    "popPercent": "Rain/snow probability",
    "precipitationMm": "Precipitation",
}


def utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def stamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone is required")
    return result.astimezone(UTC)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def region_payload(feature: dict) -> dict:
    p = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    return {
        "id": p["area_id"],
        "name": p["name"],
        "locality": p.get("locality", p["name"]),
        "province": p["province"],
        "longitude": lon,
        "latitude": lat,
        "issuedAt": p["issued_at"],
        "sourceSite": p["source_site"],
        "periods": [
            {
                "name": r["period"],
                "start": r["valid_start"],
                "end": r["valid_end"],
                "temperatureC": r.get("temperature_c"),
                "temperatureClass": r.get("temperature_class"),
                "popPercent": r.get("pop_percent"),
                "precipitationAmount": r.get("precipitation_amount"),
                "condition": r.get("condition", ""),
            }
            for r in p["periods"]
        ],
    }


def archive_bulletins(root: Path, snapshot: dict) -> None:
    from weather_ingest.eccc_city_forecasts import _atomic_json

    for feature in snapshot["features"]:
        region = region_payload(feature)
        path = resolve_under(
            root,
            Path("processed/eccc/citypage_weather/history", region["id"], digest(region) + ".json"),
        )
        if not path.exists():
            _atomic_json(path, region)


def coordinate_version(region: dict) -> str:
    return digest([region["id"], region["longitude"], region["latitude"]])


def _comparison_rows(payload: dict, source: str) -> dict:
    if source == "gdps":
        return {(h["time"], utc(stamp(h["time"]) + HOUR), "hourly"): h for h in payload["hours"]}
    result = {}
    for period in payload["periods"]:
        row = dict(period)
        amount = period.get("precipitationAmount") or ""
        # Compare a declared exact amount only. Ranges and snow depth are not totals in mm.
        match = re.fullmatch(r"(\d+(?:\.\d+)?) mm", amount)
        if match:
            row["precipitationMm"] = float(match[1])
        result[(period["start"], period["end"], period.get("temperatureClass"))] = row
    return result


def compare_versions(
    current: dict, previous: dict | None, source: str, now: datetime, thresholds: dict | None = None
) -> dict:
    thresholds = thresholds or THRESHOLDS
    result = {
        "source": "ECCC regional bulletin" if source == "bulletin" else "ECCC GDPS",
        "state": "building_history",
        "currentIssuedAt": current["issuedAt"],
        "previousIssuedAt": previous["issuedAt"] if previous else None,
        "currentVersion": digest(current),
        "previousVersion": digest(previous) if previous else None,
        "matchedPeriods": 0,
        "comparableValues": 0,
        "highlights": [],
        "details": [],
    }
    if previous is None:
        return result
    if coordinate_version(current) != coordinate_version(previous):
        result["state"] = "location_changed"
        return result
    old, new = _comparison_rows(previous, source), _comparison_rows(current, source)
    for key in sorted(old.keys() & new.keys(), key=lambda k: k[0]):
        start, end, _kind = key
        if stamp(end) <= now:
            continue
        result["matchedPeriods"] += 1
        for field, threshold in thresholds.items():
            before, after = old[key].get(field), new[key].get(field)
            if before is None or after is None:
                continue
            if (
                field == "precipitationMm"
                and source == "gdps"
                and old[key].get("precipitationStart") != new[key].get("precipitationStart")
            ):
                continue
            result["comparableValues"] += 1
            delta = after - before
            significant = abs(delta) >= threshold
            if field == "precipitationMm" and before != 0:
                significant = significant and abs(delta / before) >= 0.25
            if significant:
                result["details"].append(
                    {
                        "id": digest([source, key, field]),
                        "field": field,
                        "start": old[key]["precipitationStart"]
                        if source == "gdps" and field == "precipitationMm"
                        else start,
                        "end": old[key]["time"]
                        if source == "gdps" and field == "precipitationMm"
                        else end,
                        "before": before,
                        "after": after,
                        "delta": round(delta, 2),
                        "unit": UNITS[field],
                        "summary": f"{LABELS[field]}: {before:g} → {after:g} {UNITS[field]}",
                    }
                )
    # One representative change per field keeps hourly runs from flooding the summary.
    for field in thresholds:
        candidates = [d for d in result["details"] if d["field"] == field]
        if candidates:
            result["highlights"].append(max(candidates, key=lambda d: abs(d["delta"])))
    result["highlights"] = result["highlights"][:3]
    result["state"] = (
        "changed"
        if result["details"]
        else "unchanged"
        if result["comparableValues"]
        else "incomplete"
    )
    return result


def condition_symbol(condition: str, night: bool) -> str:
    text = condition.lower()
    if any(w in text for w in ("thunder", "storm")):
        return "cloud.bolt.rain.fill"
    if "snow" in text or "flurr" in text:
        return "cloud.snow.fill"
    if "rain" in text or "shower" in text or "drizzle" in text:
        return "cloud.rain.fill"
    if "fog" in text or "mist" in text:
        return "cloud.fog.fill"
    if "partly" in text or "mix of sun" in text or "clearing" in text:
        return "cloud.moon.fill" if night else "cloud.sun.fill"
    if "cloud" in text or "overcast" in text:
        return "cloud.fill"
    if "clear" in text or "sun" in text:
        return "moon.stars.fill" if night else "sun.max.fill"
    return "questionmark.circle"


def widget_payload(region: dict, hourly: dict | None, now: datetime) -> dict:
    periods = [p for p in region["periods"] if stamp(p["end"]) > now]
    timeline = []
    hours = hourly["hours"] if hourly else []
    model_issue = next(
        (
            stamp(h["runTime"])
            for h in hours
            if h.get("temperatureC") is not None and h.get("runTime")
        ),
        None,
    )
    if model_issue is not None and now - model_issue > 24 * HOUR:
        hours = []
    # All weather selection/summary calculation happens here, never in the extension.
    for i in range(24):
        when = now.replace(minute=0, second=0, microsecond=0) + i * HOUR
        period = next((p for p in periods if stamp(p["start"]) <= when < stamp(p["end"])), None)
        if period is None:
            continue
        hour = next((h for h in hours if stamp(h["time"]) == when), {})
        upcoming = [h for h in hours if when <= stamp(h["time"]) < when + 6 * HOUR]
        horizon = [
            p
            for p in periods
            if when <= stamp(p["start"]) < when + 24 * HOUR
            or stamp(p["start"]) <= when < stamp(p["end"])
        ]
        highs = [
            p["temperatureC"]
            for p in horizon
            if p.get("temperatureClass") == "high" and p.get("temperatureC") is not None
        ]
        lows = [
            p["temperatureC"]
            for p in horizon
            if p.get("temperatureClass") == "low" and p.get("temperatureC") is not None
        ]
        temperature = hour.get("temperatureC")
        timeline.append(
            {
                "date": utc(when),
                "validUntil": utc(when + HOUR),
                "temperatureC": temperature,
                "highC": highs[0] if highs else None,
                "lowC": lows[0] if lows else None,
                "condition": period["condition"],
                "symbol": condition_symbol(
                    period["condition"], period.get("temperatureClass") == "low"
                ),
                "popPercent": period.get("popPercent"),
                "precipitationMm": hour.get("precipitationMm"),
                "hours": [
                    {
                        "time": h["time"],
                        "temperatureC": h.get("temperatureC"),
                        "precipitationMm": h.get("precipitationMm"),
                    }
                    for h in upcoming
                ],
            }
        )
    issue = stamp(region["issuedAt"])
    return {
        "schemaVersion": 1,
        "regionId": region["id"],
        "name": region["name"],
        "locality": region.get("locality", region["name"]),
        "issuedAt": region["issuedAt"],
        "modelIssuedAt": next(
            (h["runTime"] for h in hours if h.get("temperatureC") is not None), None
        ),
        "generatedAt": utc(now),
        "source": "ECCC regional bulletin / GDPS forecast",
        "entries": timeline,
        "expiresAt": utc(
            min(
                issue + 24 * HOUR,
                stamp(periods[-1]["end"]),
                model_issue + 24 * HOUR if hours and model_issue else issue + 24 * HOUR,
            )
            if periods
            else now
        ),
        "nextRefreshAt": utc(now + timedelta(minutes=45)),
    }


class InsightWriter:
    def __init__(self, connection, loader: SqlFileLoader):
        self.connection, self.loader = connection, loader

    def query(self, name: str, parameters: dict):
        return self.connection.execute(self.loader.load(f"insights/{name}.sql"), parameters)

    def revision(self, payload: dict, source: str):
        self.query(
            "insert_revision",
            {
                "area_id": payload["id"],
                "source": source,
                "version": digest(payload),
                "issued_at": payload["issuedAt"],
                "coordinate_version": coordinate_version(payload),
                "payload": Jsonb(payload),
            },
        )

    def publish(self, area: str, kind: str, payload: dict, now: datetime, end: datetime):
        content = {k: v for k, v in payload.items() if k not in {"generatedAt", "nextRefreshAt"}}
        self.query(
            "publish",
            {
                "area_id": area,
                "kind": kind,
                "payload": Jsonb(payload),
                "version": digest(content),
                "generated_at": now,
                "valid_until": end,
            },
        )


def sample_model_runs(assets: list[dict], regions: list[dict], root: Path) -> dict:
    runs = defaultdict(lambda: {r["id"]: {} for r in regions})
    for asset in assets:
        field, unit, scale = FIELDS[asset["field"]]
        if asset["unit"] != unit:
            continue
        if (
            field == "precipitationMm"
            and asset["interval_start"] is not None
            and asset["valid_time"] - asset["interval_start"] != HOUR
        ):
            continue
        try:
            path = resolve_under(root, Path(asset["relative_path"]))
            if path.is_symlink():
                continue
            with rasterio.open(path) as dataset:
                xs, ys = transform(
                    "EPSG:4326",
                    dataset.crs,
                    [r["longitude"] for r in regions],
                    [r["latitude"] for r in regions],
                )
                values = list(dataset.sample(zip(xs, ys, strict=True), indexes=1, masked=True))
            for region, value in zip(regions, values, strict=True):
                if bool(value.mask[0]):
                    continue
                number = float(value[0]) * scale
                if not math.isfinite(number) or (field != "temperatureC" and number < 0):
                    continue
                if field == "relativeHumidityPercent" and number > 100:
                    continue
                runs[asset["run_time"]][region["id"]].setdefault(utc(asset["valid_time"]), {})[
                    field
                ] = round(number, 2)
        except (OSError, ValueError, rasterio.errors.RasterioError):
            LOG.warning("forecast_batch_asset_unavailable", exc_info=True)
    return runs


def hour_rows(samples: dict, times: list[datetime], run: datetime) -> list[dict]:
    rows = []
    for valid in times:
        values = {key: samples.get(utc(valid), {}).get(key) for key, _, _ in FIELDS.values()}
        count = sum(v is not None for v in values.values())
        rows.append(
            {
                "time": utc(valid),
                "runTime": utc(run),
                "precipitationStart": utc(valid - HOUR),
                **values,
                "status": "complete" if count == len(values) else "partial" if count else "missing",
            }
        )
    return rows


def prepare_forecasts(settings: Settings, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    path = settings.data_root / "processed/eccc/citypage_weather/latest.json"
    snapshot = json.loads(path.read_bytes())
    archive_bulletins(settings.data_root, snapshot)
    config_path = Path(os.getenv("WEATHER_CONFIG_ROOT", "config")) / "forecast_insights.json"
    config = json.loads(config_path.read_bytes())
    provinces = set(config["provinces"])
    maximum_regions = config["maximum_regions"]
    thresholds = config["highlight_thresholds"]
    if not 1 <= maximum_regions <= 128 or not provinces <= {
        "NS",
        "NB",
        "PE",
        "NL",
        "QC",
        "ON",
        "MB",
        "SK",
        "AB",
        "BC",
        "YT",
        "NT",
        "NU",
    }:
        raise ValueError("Invalid forecast preparation coverage")
    if set(thresholds) != set(THRESHOLDS) or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
        for v in thresholds.values()
    ):
        raise ValueError("Forecast highlight thresholds must be finite and positive")
    regions = [region_payload(f) for f in snapshot["features"]]
    selected = [r for r in regions if r["province"] in provinces][:maximum_regions]
    loader = SqlFileLoader(settings.sql_root)
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        writer = InsightWriter(connection, loader)
        for region in regions:
            history = settings.data_root / "processed/eccc/citypage_weather/history" / region["id"]
            for archive in sorted(history.glob("*.json"), key=lambda p: p.stat().st_mtime)[-64:]:
                payload = json.loads(archive.read_bytes())
                if stamp(payload["issuedAt"]) >= now - timedelta(days=30):
                    writer.revision(payload, "bulletin")
        connection.commit()
        assets = writer.query("model_assets", {"now": now, "fields": list(FIELDS)}).fetchall()
        batches = sample_model_runs(assets, selected, settings.data_root)
        start = now.replace(minute=0, second=0, microsecond=0)
        for region in regions:
            area = region["id"]
            for run, by_region in batches.items():
                hours = hour_rows(by_region.get(area, {}), [run + i * HOUR for i in range(85)], run)
                if sum(h["temperatureC"] is not None for h in hours) >= 60:
                    writer.revision(
                        {
                            **region,
                            "issuedAt": utc(run),
                            "periods": [],
                            "hours": hours,
                            "product": "gdps",
                            "domain": "global",
                        },
                        "gdps",
                    )
            groups = []
            hourly = None
            for source in ("bulletin", "gdps"):
                revisions = writer.query(
                    "revisions", {"area_id": area, "source": source}
                ).fetchall()
                if not revisions:
                    continue
                current = revisions[0]["payload"]
                # Revisions of a partially arriving model run aren't distinct forecast cycles.
                previous = next(
                    (
                        r["payload"]
                        for r in revisions[1:]
                        if source == "bulletin" or r["issued_at"] < revisions[0]["issued_at"]
                    ),
                    None,
                )
                groups.append(compare_versions(current, previous, source, now, thresholds))
                if source == "gdps":
                    by_time = {h["time"]: h for h in current["hours"]}
                    hours = [
                        by_time.get(
                            utc(start + i * HOUR),
                            hour_rows({}, [start + i * HOUR], stamp(current["issuedAt"]))[0],
                        )
                        for i in range(72)
                    ]
                    hourly = {
                        "regionId": area,
                        "latitude": region["latitude"],
                        "longitude": region["longitude"],
                        "source": "ECCC GDPS",
                        "generatedAt": utc(now),
                        "start": utc(start),
                        "end": utc(start + 72 * HOUR),
                        "hours": hours,
                        "availableHours": sum(h["status"] != "missing" for h in hours),
                        "completeHours": sum(h["status"] == "complete" for h in hours),
                    }
                    writer.publish(area, "hourly", hourly, now, now + HOUR)
            writer.publish(
                area,
                "changes",
                {"schemaVersion": 1, "regionId": area, "generatedAt": utc(now), "groups": groups},
                now,
                now + HOUR,
            )
            widget = widget_payload(region, hourly, now)
            writer.publish(area, "widget", widget, now, stamp(widget["expiresAt"]))
            connection.commit()
    return {"regions": len(regions), "sampledRegions": len(selected), "assets": len(assets)}


if __name__ == "__main__":
    print(json.dumps(prepare_forecasts(Settings.from_environment())))
