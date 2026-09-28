"""Collect and normalize ECCC's official public 24-hour city forecasts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from weather_ingest.eccc_city_forecasts import (
    ECCC_CITYPAGE_ATTRIBUTION,
    _atomic_json,
    _utc_text,
    citypage_latest_relative_path,
)
from weather_ingest.storage import resolve_under

ECCC_HOURLY_API_URL = "https://weather.gc.ca/api/app/v3/en/Location"
ECCC_HOURLY_PAGE_URL = "https://weather.gc.ca/en/forecast/hourly/index.html"
AREA_ID = re.compile(r"^[a-f0-9]{16}$")
WIND_DIRECTION = re.compile(r"^[A-Z]{1,12}$")


def _positive_integer(
    values: dict[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


@dataclass(frozen=True, slots=True)
class HourlyForecastSettings:
    """Resource and provider bounds for official hourly forecast collection."""

    maximum_regions: int = 1_200
    maximum_download_bytes: int = 2 * 1024**2
    minimum_free_bytes: int = 1024**3
    timeout_seconds: int = 60
    parallel_downloads: int = 8

    def __post_init__(self) -> None:
        if self.maximum_regions < 1 or self.maximum_download_bytes < 1:
            raise ValueError("hourly forecast collection bounds must be positive")
        if self.minimum_free_bytes < 0:
            raise ValueError("hourly forecast minimum free space cannot be negative")
        if self.timeout_seconds < 1:
            raise ValueError("hourly forecast timeout must be positive")
        if not 1 <= self.parallel_downloads <= 16:
            raise ValueError("hourly forecast parallel downloads must be between 1 and 16")

    @classmethod
    def from_environment(
        cls,
        values: dict[str, str] | None = None,
    ) -> HourlyForecastSettings:
        environment = dict(os.environ) if values is None else values
        return cls(
            maximum_regions=_positive_integer(
                environment,
                "ECCC_HOURLY_FORECAST_MAXIMUM_REGIONS",
                1_200,
            ),
            maximum_download_bytes=_positive_integer(
                environment,
                "ECCC_HOURLY_FORECAST_MAXIMUM_DOWNLOAD_BYTES",
                2 * 1024**2,
            ),
            minimum_free_bytes=_positive_integer(
                environment,
                "ECCC_HOURLY_FORECAST_MINIMUM_FREE_BYTES",
                1024**3,
                minimum=0,
            ),
            timeout_seconds=_positive_integer(
                environment,
                "ECCC_HOURLY_FORECAST_TIMEOUT_SECONDS",
                60,
            ),
            parallel_downloads=_positive_integer(
                environment,
                "ECCC_HOURLY_FORECAST_PARALLEL_DOWNLOADS",
                8,
            ),
        )


def hourly_forecast_archive() -> Path:
    return Path("processed", "eccc", "hourly_forecast")


def hourly_forecast_latest_relative_path() -> Path:
    return hourly_forecast_archive() / "latest.json"


def hourly_forecast_manifest_relative_path() -> Path:
    return hourly_forecast_archive() / "manifest.json"


def _history_relative_path(collected_at: datetime, digest: str) -> Path:
    return (
        hourly_forecast_archive()
        / "history"
        / collected_at.strftime(f"%Y/%m/%d/%Y%m%dT%H%M%SZ_{digest[:12]}.json")
    )


def _finite_number(value: object, *, minimum: float, maximum: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        return None
    return parsed


def _optional_number(value: object, *, minimum: float, maximum: float) -> float | None:
    if value is None or value == "":
        return None
    parsed = _finite_number(value, minimum=minimum, maximum=maximum)
    if parsed is None:
        raise ValueError("official hourly forecast contains an invalid numeric value")
    return parsed


def _metric(container: object, *, minimum: float, maximum: float) -> float | None:
    if not isinstance(container, dict):
        return None
    return _optional_number(container.get("metric"), minimum=minimum, maximum=maximum)


def _wind_metric(container: object) -> float | None:
    if not isinstance(container, dict):
        return None
    value = container.get("metric")
    if isinstance(value, str) and value.strip().casefold() == "calm":
        return 0.0
    return _optional_number(value, minimum=0, maximum=500)


def _required_text(value: object, name: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"official hourly forecast has invalid {name}")
    return value.strip()


def _region_inventory(data_root: Path, maximum_regions: int) -> list[dict[str, Any]]:
    path = resolve_under(data_root, citypage_latest_relative_path())
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(
            "collect ECCC City Page forecasts before collecting official hourly forecasts"
        )
    if not 0 < path.stat().st_size <= 64 * 1024**2:
        raise ValueError("invalid ECCC City Page region snapshot size")
    snapshot = json.loads(path.read_bytes())
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != 1
        or snapshot.get("provider") != "eccc"
        or snapshot.get("product") != "citypage_weather"
        or snapshot.get("type") != "FeatureCollection"
        or not isinstance(snapshot.get("features"), list)
    ):
        raise ValueError("invalid ECCC City Page region snapshot contract")
    if not 0 < len(snapshot["features"]) <= maximum_regions:
        raise ValueError("ECCC City Page region count is outside the configured bound")
    regions: list[dict[str, Any]] = []
    for feature in snapshot["features"]:
        props = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geometry, dict):
            raise ValueError("invalid forecast region")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("invalid forecast region coordinates")
        longitude = _finite_number(coordinates[0], minimum=-180, maximum=180)
        latitude = _finite_number(coordinates[1], minimum=-90, maximum=90)
        area_id = props.get("area_id")
        province = props.get("province")
        if longitude is None or latitude is None:
            raise ValueError("invalid forecast region coordinates")
        if not isinstance(area_id, str) or not AREA_ID.fullmatch(area_id):
            raise ValueError("invalid forecast region identifier")
        if not isinstance(province, str) or not re.fullmatch(r"[A-Z]{2}", province):
            raise ValueError("invalid forecast region province")
        regions.append(
            {
                "area_id": area_id,
                "name": _required_text(props.get("name"), "region name"),
                "locality": _required_text(
                    props.get("locality", props.get("name")),
                    "region locality",
                ),
                "province": province,
                "longitude": longitude,
                "latitude": latitude,
            }
        )
    return sorted(regions, key=lambda item: item["area_id"])


def normalize_hourly_response(
    payload: object,
    region: dict[str, Any],
    *,
    collected_at: datetime,
) -> dict[str, Any]:
    """Validate one official app response and retain its 24 hourly rows."""

    if collected_at.tzinfo is None:
        raise ValueError("hourly forecast collection time must be timezone-aware")
    if not isinstance(payload, list) or not payload or len(payload) > 10:
        raise ValueError("official hourly forecast response must be a bounded location list")
    candidates = [item for item in payload if isinstance(item, dict)]
    if not candidates:
        raise ValueError("official hourly forecast response contains no location")

    def distance(item: dict[str, Any]) -> float:
        value = _finite_number(item.get("distance"), minimum=0, maximum=20_000)
        return value if value is not None else math.inf

    location = min(candidates, key=distance)
    if distance(location) > 200:
        raise ValueError("official hourly forecast location is more than 200 km away")
    if str(location.get("province", "")).upper() != region["province"]:
        raise ValueError("official hourly forecast province does not match its region")
    provider_latitude = _finite_number(location.get("lat"), minimum=-90, maximum=90)
    provider_longitude = _finite_number(location.get("lon"), minimum=-180, maximum=180)
    if provider_latitude is None or provider_longitude is None:
        raise ValueError("official hourly forecast location has invalid coordinates")
    timezone = _required_text(location.get("timezone"), "time zone", maximum=100)
    provider_name = _required_text(location.get("displayName"), "location name")
    hourly_forecast = location.get("hourlyFcst")
    mtimes = location.get("mtimes")
    if not isinstance(hourly_forecast, dict) or not isinstance(mtimes, dict):
        raise ValueError("official hourly forecast metadata is missing")
    issued_epoch = _finite_number(
        mtimes.get("HOURLY_FORECAST"),
        minimum=1,
        maximum=collected_at.timestamp() + 15 * 60,
    )
    if issued_epoch is None:
        raise ValueError("official hourly forecast issue time is invalid")
    issued_at = datetime.fromtimestamp(issued_epoch, UTC)
    if collected_at.astimezone(UTC) - issued_at > timedelta(hours=48):
        raise ValueError("official hourly forecast is more than 48 hours old")
    source_hours = hourly_forecast.get("hourly")
    if not isinstance(source_hours, list) or len(source_hours) != 24:
        raise ValueError("official hourly forecast must contain exactly 24 hours")

    hours: list[dict[str, Any]] = []
    for source in source_hours:
        if not isinstance(source, dict):
            raise ValueError("official hourly forecast hour must be an object")
        epoch = _finite_number(
            source.get("epochTime"),
            minimum=1,
            maximum=(collected_at + timedelta(days=3)).timestamp(),
        )
        if epoch is None or not epoch.is_integer():
            raise ValueError("official hourly forecast valid time is invalid")
        condition = _required_text(source.get("condition"), "condition")
        pop = _optional_number(source.get("precip"), minimum=0, maximum=100)
        icon_code = str(source.get("iconCode", "")).strip()
        if not re.fullmatch(r"\d{1,3}", icon_code):
            raise ValueError("official hourly forecast icon code is invalid")
        wind_direction = str(source.get("windDir", "")).strip().upper() or None
        if wind_direction is not None and not WIND_DIRECTION.fullmatch(wind_direction):
            raise ValueError("official hourly forecast wind direction is invalid")
        uv = source.get("uv")
        hours.append(
            {
                "valid_time": _utc_text(datetime.fromtimestamp(epoch, UTC)),
                "condition": condition,
                "pop_percent": pop,
                "temperature_c": _metric(source.get("temperature"), minimum=-100, maximum=70),
                "feels_like_c": _metric(source.get("feelsLike"), minimum=-150, maximum=100),
                "icon_code": icon_code,
                "wind_speed_kmh": _wind_metric(source.get("windSpeed")),
                "wind_direction": wind_direction,
                "wind_gust_kmh": _wind_metric(source.get("windGust")),
                "uv_index": (
                    _optional_number(uv.get("index"), minimum=0, maximum=30)
                    if isinstance(uv, dict)
                    else None
                ),
            }
        )
    valid_times = [
        datetime.fromisoformat(hour["valid_time"].replace("Z", "+00:00")) for hour in hours
    ]
    if valid_times != sorted(set(valid_times)) or any(
        right - left != timedelta(hours=1)
        for left, right in zip(valid_times, valid_times[1:], strict=False)
    ):
        raise ValueError("official hourly forecast hours must be unique and consecutive")
    if abs((valid_times[0] - collected_at.astimezone(UTC)).total_seconds()) > 6 * 3600:
        raise ValueError("official hourly forecast does not start near collection time")
    return {
        "area_id": region["area_id"],
        "name": region["name"],
        "locality": region["locality"],
        "province": region["province"],
        "latitude": region["latitude"],
        "longitude": region["longitude"],
        "provider_location": provider_name,
        "provider_latitude": provider_latitude,
        "provider_longitude": provider_longitude,
        "timezone": timezone,
        "issued_at": _utc_text(issued_at),
        "source_url": (
            f"{ECCC_HOURLY_PAGE_URL}?coords={provider_latitude:.5f},{provider_longitude:.5f}"
        ),
        "hours": hours,
    }


def _collect_region(
    client: httpx.Client,
    region: dict[str, Any],
    maximum_download_bytes: int,
    collected_at: datetime,
) -> dict[str, Any]:
    coordinate = f"{region['latitude']:.5f},{region['longitude']:.5f}"
    response = client.get(f"{ECCC_HOURLY_API_URL}/{coordinate}", params={"type": "city"})
    response.raise_for_status()
    if not 0 < len(response.content) <= maximum_download_bytes:
        raise ValueError(f"official hourly forecast response for {region['area_id']} is invalid")
    return normalize_hourly_response(response.json(), region, collected_at=collected_at)


def _content_digest(regions: list[dict[str, Any]]) -> str:
    payload = json.dumps(regions, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _read_manifest(data_root: Path) -> dict[str, Any]:
    path = resolve_under(data_root, hourly_forecast_manifest_relative_path())
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("product") != "hourly_forecast"
    ):
        return {}
    return payload


def ingest_hourly_forecasts(
    settings: HourlyForecastSettings,
    data_root: Path,
    *,
    now: datetime | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Collect all official hourly regions and atomically publish a snapshot."""

    collected_at = now or datetime.now(UTC)
    if collected_at.tzinfo is None:
        raise ValueError("hourly forecast collection time must be timezone-aware")
    data_root.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(data_root).free
    if free_bytes < settings.minimum_free_bytes:
        raise OSError(
            f"hourly forecast ingestion requires {settings.minimum_free_bytes} "
            f"free bytes but only {free_bytes} are available"
        )
    inventory = _region_inventory(data_root, settings.maximum_regions)
    timeout = httpx.Timeout(settings.timeout_seconds, connect=15.0)
    headers = {"User-Agent": "weather-platform-official-hourly-forecast/0.1"}
    with (
        httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            transport=transport,
        ) as client,
        ThreadPoolExecutor(max_workers=settings.parallel_downloads) as executor,
    ):
        regions = list(
            executor.map(
                lambda region: _collect_region(
                    client,
                    region,
                    settings.maximum_download_bytes,
                    collected_at,
                ),
                inventory,
            )
        )
    regions.sort(key=lambda item: item["area_id"])
    if len(regions) != len(inventory):
        raise ValueError("official hourly forecast collection did not cover every region")
    digest = _content_digest(regions)
    previous = _read_manifest(data_root)
    latest_path = resolve_under(data_root, hourly_forecast_latest_relative_path())
    status = (
        "unchanged"
        if previous.get("content_sha256") == digest
        and latest_path.is_file()
        and not latest_path.is_symlink()
        else "updated"
    )
    issued = [str(region["issued_at"]) for region in regions]
    snapshot = {
        "schema_version": 1,
        "provider": "eccc",
        "product": "hourly_forecast",
        "generated_at": _utc_text(collected_at),
        "region_count": len(regions),
        "available_start": min(
            hour["valid_time"] for region in regions for hour in region["hours"]
        ),
        "available_end": max(hour["valid_time"] for region in regions for hour in region["hours"]),
        "source_issued_at_min": min(issued),
        "source_issued_at_max": max(issued),
        "attribution": ECCC_CITYPAGE_ATTRIBUTION,
        "source": "ECCC official public hourly forecast",
        "regions": regions,
    }
    if status == "updated":
        _atomic_json(latest_path, snapshot)
        _atomic_json(
            resolve_under(data_root, _history_relative_path(collected_at, digest)), snapshot
        )
    latest_bytes = latest_path.read_bytes()
    manifest = {
        "schema_version": 1,
        "provider": "eccc",
        "product": "hourly_forecast",
        "collected_at": _utc_text(collected_at),
        "status": status,
        "region_count": len(regions),
        "hour_count": sum(len(region["hours"]) for region in regions),
        "content_sha256": digest,
        "snapshot": {
            "relative_path": hourly_forecast_latest_relative_path().as_posix(),
            "size_bytes": len(latest_bytes),
            "sha256": hashlib.sha256(latest_bytes).hexdigest(),
        },
    }
    _atomic_json(
        resolve_under(data_root, hourly_forecast_manifest_relative_path()),
        manifest,
    )
    return {
        "status": status,
        "region_count": len(regions),
        "hour_count": manifest["hour_count"],
        "source_issued_at_min": min(issued),
        "source_issued_at_max": max(issued),
        "snapshot_relative_path": hourly_forecast_latest_relative_path().as_posix(),
    }
