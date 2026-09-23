"""Catalogue, layer-resolution, and point-sampling API."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import re
import shutil
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import rasterio
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from pyproj import Transformer
from redis.exceptions import RedisError
from rio_tiler.errors import PointOutsideBounds
from rio_tiler.io import COGReader
from starlette.concurrency import run_in_threadpool
from weather_common import __version__
from weather_common.db import Database, SqlFileLoader
from weather_common.display_scales import palette_for_display, rounded_temperature_range
from weather_common.layer_tokens import LayerTokenPayload, create_layer_token
from weather_common.metrics import (
    OPERATION_DURATION,
    observe_http_request,
    prometheus_response,
    update_smoke_metrics,
)
from weather_common.settings import Settings
from weather_ingest.fbp_fuels import has_supported_cffeps_fuel
from weather_ingest.fire_scenarios import SmokeScenarioConfig
from weather_ingest.flexpart_releases import (
    MAXIMUM_RELEASE_GROUPS_PER_EVENT_HOUR,
    MINIMUM_PARTICLES_PER_RELEASE,
)
from weather_tiles.rendering import resolve_asset_path

from weather_api.forecast import (
    hourly_outlook,
    nearest_region,
    precipitation_outlook,
    regional_outlooks,
)
from weather_api.golf import GolfLimits, collect_point, golf_outlook, playing_windows
from weather_api.imagery import router as imagery_router
from weather_api.insights import prepared_hourly
from weather_api.insights import router as insights_router
from weather_api.repository import (
    CatalogueNotFoundError,
    CatalogueReader,
    PostgresCatalogueRepository,
)
from weather_api.schemas import (
    DomainCollection,
    DomainSummary,
    FieldCollection,
    FieldSummary,
    IngestionStatus,
    IngestionStatusCollection,
    Legend,
    PaletteStop,
    ProductCollection,
    ProductSummary,
    ResolvedLayer,
    RunCollection,
    RunSummary,
    SampleResponse,
    SampleValue,
    TimeCollection,
    TimelineCollection,
    TimelineFrameSummary,
    TimeSummary,
    VariableCollection,
    VariableSummary,
    WindVectorCollection,
    WindVectorFeature,
    WindVectorGeometry,
    WindVectorProperties,
)
from weather_api.simulation_repository import (
    PostgresSimulationRepository,
    SimulationNotFoundError,
    SimulationQueueCapacityError,
    SimulationRepository,
)
from weather_api.simulation_schemas import (
    RevisionCreate,
    RevisionSummary,
    RunCreate,
    RunSubmission,
    ScenarioCreate,
    ScenarioSummary,
    SimulationRunSummary,
)
from weather_api.smoke_preflight import (
    SmokeAdmissionLimits,
    SmokePreflightError,
    SmokePreflightResult,
    preflight_smoke_scenario,
)

logger = logging.getLogger("weather_api")
settings = Settings.from_environment()
PUBLIC_CODE = r"^[a-z][a-z0-9_]{0,63}$"
HOTSPOT_ARCHIVE = Path("processed", "nrcan", "cwfis", "firem3")
CITY_FORECAST_SNAPSHOT = Path(
    "processed",
    "eccc",
    "citypage_weather",
    "latest.json",
)
WIND_U_FIELD = "wind_u_10m"
WIND_V_FIELD = "wind_v_10m"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    database = Database(
        settings.database_url,
        min_size=1,
        max_size=8,
        loader=SqlFileLoader(settings.sql_root),
    )
    await database.open()
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    application.state.database = database
    application.state.redis = redis_client
    try:
        yield
    finally:
        await redis_client.aclose()
        await database.close()


app = FastAPI(
    title="Weather Platform API",
    version=__version__,
    description="Catalogue and point-query API for processed ECCC weather products.",
    lifespan=lifespan,
)
app.include_router(imagery_router)
app.include_router(insights_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))[:128]
    started = time.perf_counter()
    status = 500
    try:
        response = await observe_http_request("weather-api", request, call_next)
        status = response.status_code
    finally:
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
    response.headers["x-request-id"] = request_id
    return response


def get_repository(request: Request) -> CatalogueReader:
    try:
        database = request.app.state.database
        return PostgresCatalogueRepository(database.pool, database.loader)
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="Catalogue database is not ready") from exc


def get_simulation_repository(request: Request) -> SimulationRepository:
    try:
        database = request.app.state.database
        return PostgresSimulationRepository(database.pool, database.loader)
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="Simulation database is not ready") from exc


def _aware(value: datetime, parameter: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail=f"{parameter} must include a UTC offset")
    return value.astimezone(UTC)


def _palette_stops(definition: dict[str, Any]) -> list[PaletteStop]:
    raw_stops = definition.get("stops")
    if not isinstance(raw_stops, list):
        raise HTTPException(status_code=500, detail="The registered palette is invalid")
    try:
        return [PaletteStop.model_validate(stop) for stop in raw_stops]
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="The registered palette is invalid") from exc


@app.exception_handler(CatalogueNotFoundError)
async def catalogue_not_found(_request: Request, _error: CatalogueNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": "No matching processed asset was found"}
    )


@app.exception_handler(SimulationNotFoundError)
async def simulation_not_found(_request: Request, _error: SimulationNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Simulation object was not found"})


@app.exception_handler(SimulationQueueCapacityError)
async def simulation_queue_full(
    _request: Request, error: SimulationQueueCapacityError
) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(error)})


def _require_simulation_writes() -> None:
    if not settings.simulation_writes_enabled:
        raise HTTPException(
            status_code=503,
            detail="Smoke simulation submission is disabled pending local scientific validation",
        )


def _smoke_admission_limits() -> SmokeAdmissionLimits:
    return SmokeAdmissionLimits(
        maximum_horizon_hours=settings.smoke_max_horizon_hours,
        maximum_domain_cells=settings.smoke_max_domain_cells,
        maximum_particles=settings.smoke_maximum_particles,
        maximum_releases=settings.smoke_maximum_releases,
        minimum_free_bytes=settings.smoke_minimum_free_bytes,
        maximum_storage_bytes=settings.smoke_maximum_storage_bytes,
    )


async def _preflight_smoke_scenario(
    config: SmokeScenarioConfig,
) -> SmokePreflightResult:
    try:
        return await run_in_threadpool(
            preflight_smoke_scenario,
            settings.data_root,
            config,
            _smoke_admission_limits(),
        )
    except SmokePreflightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/smoke/capabilities", tags=["smoke"])
async def smoke_capabilities() -> dict[str, Any]:
    """Describe bounded inputs using the latest complete local GFS archive."""

    cycle: datetime | None = None
    available_start: datetime | None = None
    available_end: datetime | None = None
    manifests = sorted(
        settings.data_root.glob("raw/noaa/gfs/global_1p00/*/*/*/*/manifest.json"),
        reverse=True,
    )
    for manifest in manifests:
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            payload = await run_in_threadpool(
                lambda path=manifest: json.loads(path.read_text(encoding="utf-8"))
            )
            files = payload["files"]
            if not files:
                continue
            cycle = datetime.fromisoformat(payload["initialization_time"].replace("Z", "+00:00"))
            available_start = min(
                datetime.fromisoformat(item["valid_time"].replace("Z", "+00:00")) for item in files
            )
            available_end = max(
                datetime.fromisoformat(item["valid_time"].replace("Z", "+00:00")) for item in files
            )
            if available_end > available_start:
                break
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            cycle = available_start = available_end = None
    return {
        "writesEnabled": settings.simulation_writes_enabled,
        "validationRunsEnabled": settings.smoke_validation_runs_enabled,
        "latestCompleteGfsCycle": cycle,
        "availableStart": available_start,
        "availableEnd": available_end,
        "maximumHorizonHours": settings.smoke_max_horizon_hours,
        "species": ["PM25", "CO", "BC"],
        "uncertaintyModes": ["low", "central", "high"],
        "gridSpacingDegrees": [0.25, 0.5, 1.0],
        "maximumParticles": settings.smoke_maximum_particles,
        "maximumReleaseGroupsPerEventHour": MAXIMUM_RELEASE_GROUPS_PER_EVENT_HOUR,
        "minimumParticlesPerRelease": MINIMUM_PARTICLES_PER_RELEASE,
        "maximumDomainCells": settings.smoke_max_domain_cells,
        "maximumReleases": settings.smoke_maximum_releases,
        "maximumQueuedRuns": settings.smoke_max_queued_runs,
        "maximumStorageBytes": settings.smoke_maximum_storage_bytes,
        "primaryEmissionsOnly": True,
    }


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok", "service": "weather-api", "version": __version__}


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    try:
        async with (
            request.app.state.database.pool.connection(timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                request.app.state.database.loader.load("simulation/metrics_snapshot.sql")
            )
            snapshot = await cursor.fetchone()
        free_bytes = await run_in_threadpool(lambda: shutil.disk_usage(settings.data_root).free)
        update_smoke_metrics(
            snapshot or {},
            free_bytes=free_bytes,
            minimum_free_bytes=settings.smoke_minimum_free_bytes,
        )
    except Exception as exc:
        logger.warning("smoke_metrics_refresh_failed", extra={"error_class": type(exc).__name__})
    return prometheus_response()


def _hotspot_snapshot_entry(data_root: Path, data_date: date) -> dict[str, Any] | None:
    archive = data_root / HOTSPOT_ARCHIVE
    directory = archive / f"{data_date:%Y}" / f"{data_date:%m}" / f"{data_date:%d}"
    manifest_path = directory / "manifest.json"
    geojson_path = directory / "hotspots_viirs.geojson"
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or manifest_path.stat().st_size > 1024**2
        or not geojson_path.is_file()
        or geojson_path.is_symlink()
    ):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    geojson = manifest.get("geojson")
    feature_count = manifest.get("feature_count")
    expected_relative = HOTSPOT_ARCHIVE / directory.relative_to(archive) / geojson_path.name
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("provider") != "nrcan"
        or manifest.get("product") != "cwfis_firem3_hotspots"
        or manifest.get("data_date") != data_date.isoformat()
        or not isinstance(geojson, dict)
        or geojson.get("relative_path") != expected_relative.as_posix()
        or geojson.get("size_bytes") != geojson_path.stat().st_size
        or isinstance(feature_count, bool)
        or not isinstance(feature_count, int)
        or feature_count < 0
    ):
        return None
    bbox = manifest.get("bbox")
    if not (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(isinstance(value, int | float) for value in bbox)
    ):
        bbox = None
    return {
        "dataDate": data_date.isoformat(),
        "featureCount": feature_count,
        "firstObservation": manifest.get("first_observation"),
        "lastObservation": manifest.get("last_observation"),
        "bbox": bbox,
        "path": geojson_path,
    }


def _hotspot_snapshot_catalogue(data_root: Path) -> dict[str, Any]:
    archive = data_root / HOTSPOT_ARCHIVE
    items: list[dict[str, Any]] = []
    if archive.is_dir() and not archive.is_symlink():
        for manifest_path in archive.glob("*/*/*/manifest.json"):
            try:
                data_date = date(
                    int(manifest_path.parents[2].name),
                    int(manifest_path.parents[1].name),
                    int(manifest_path.parent.name),
                )
            except ValueError:
                continue
            entry = _hotspot_snapshot_entry(data_root, data_date)
            if entry is not None:
                items.append({key: value for key, value in entry.items() if key != "path"})
    items.sort(key=lambda item: item["dataDate"])
    return {
        "items": items,
        "availableStart": items[0]["dataDate"] if items else None,
        "availableEnd": items[-1]["dataDate"] if items else None,
    }


@app.get("/api/v1/hotspots/dates", tags=["wildfire"])
async def wildfire_hotspot_dates() -> dict[str, Any]:
    """List every validated daily CWFIS VIIRS snapshot in local storage."""

    return await run_in_threadpool(_hotspot_snapshot_catalogue, settings.data_root)


@app.get("/api/v1/hotspots", tags=["wildfire"])
async def wildfire_hotspots(
    request: Request,
    data_date: Annotated[date | None, Query(alias="date")] = None,
) -> Response:
    """Serve the latest or a requested map-ready CWFIS VIIRS snapshot."""

    if data_date is None:
        path = settings.data_root / HOTSPOT_ARCHIVE / "latest.geojson"
    else:
        entry = await run_in_threadpool(_hotspot_snapshot_entry, settings.data_root, data_date)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"No CWFIS hotspot snapshot is available for {data_date.isoformat()}",
            )
        path = entry["path"]
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="No CWFIS hotspot snapshot is available")
    size_bytes = path.stat().st_size
    if size_bytes <= 0 or size_bytes > 128 * 1024**2:
        raise HTTPException(status_code=503, detail="The CWFIS hotspot snapshot is invalid")
    content = await run_in_threadpool(path.read_bytes)
    etag = f'"{hashlib.sha256(content).hexdigest()}"'
    headers = {
        "Cache-Control": "public, max-age=300, must-revalidate",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if data_date is not None:
        headers["X-Hotspot-Data-Date"] = data_date.isoformat()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content, media_type="application/geo+json", headers=headers)


def _parse_snapshot_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _city_forecast_frame(
    content: bytes,
    valid_time: datetime,
    province: str | None,
) -> dict[str, Any]:
    try:
        snapshot = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("city forecast snapshot is not valid JSON") from exc
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("type") != "FeatureCollection"
        or snapshot.get("schema_version") != 1
        or snapshot.get("provider") != "eccc"
        or snapshot.get("product") != "citypage_weather"
        or not isinstance(snapshot.get("features"), list)
    ):
        raise ValueError("city forecast snapshot has an invalid data contract")
    selected_features: list[dict[str, Any]] = []
    for feature in snapshot["features"]:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            continue
        feature_province = properties.get("province")
        if province is not None and feature_province != province:
            continue
        periods = properties.get("periods")
        if not isinstance(periods, list):
            continue
        selected_period: dict[str, Any] | None = None
        for period in periods:
            if not isinstance(period, dict):
                continue
            try:
                start = _parse_snapshot_time(
                    period.get("valid_start"),
                    label="period start",
                )
                end = _parse_snapshot_time(
                    period.get("valid_end"),
                    label="period end",
                )
            except (TypeError, ValueError):
                continue
            if start <= valid_time < end:
                selected_period = period
                break
        if selected_period is None:
            continue
        selected_features.append(
            {
                "type": "Feature",
                "id": feature.get("id"),
                "geometry": geometry,
                "properties": {
                    "areaId": properties.get("area_id"),
                    "name": properties.get("name"),
                    "locality": properties.get("locality") or properties.get("name"),
                    "province": feature_province,
                    "issuedAt": properties.get("issued_at"),
                    "sourceSite": properties.get("source_site"),
                    "period": selected_period.get("period"),
                    "validStart": selected_period.get("valid_start"),
                    "validEnd": selected_period.get("valid_end"),
                    "temperatureC": selected_period.get("temperature_c"),
                    "temperatureClass": selected_period.get("temperature_class"),
                    "relativeHumidityPercent": selected_period.get("relative_humidity_percent"),
                    "popPercent": selected_period.get("pop_percent"),
                    "precipitationAmount": selected_period.get("precipitation_amount"),
                    "condition": selected_period.get("condition"),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "provider": "eccc",
        "product": "citypage_weather",
        "generatedAt": snapshot.get("generated_at"),
        "issuedAt": snapshot.get("issued_at"),
        "validTime": valid_time.isoformat().replace("+00:00", "Z"),
        "availableStart": snapshot.get("available_start"),
        "availableEnd": snapshot.get("available_end"),
        "featureCount": len(selected_features),
        "attribution": snapshot.get("attribution"),
        "licenseUrl": snapshot.get("license_url"),
        "features": selected_features,
    }


@app.get("/api/v1/city-forecasts", tags=["forecast"])
async def city_forecasts(
    request: Request,
    valid_time: Annotated[datetime | None, Query()] = None,
    province: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
) -> Response:
    """Serve official regional text forecasts for one requested UTC instant."""

    selected_time = (
        _aware(valid_time, "valid_time") if valid_time is not None else datetime.now(UTC)
    )
    path = settings.data_root / CITY_FORECAST_SNAPSHOT
    if not path.is_file() or path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="No ECCC city forecast snapshot is available",
        )
    size_bytes = path.stat().st_size
    if size_bytes <= 0 or size_bytes > 64 * 1024**2:
        raise HTTPException(
            status_code=503,
            detail="The ECCC city forecast snapshot is invalid",
        )
    content = await run_in_threadpool(path.read_bytes)
    try:
        frame = await run_in_threadpool(
            _city_forecast_frame,
            content,
            selected_time,
            province,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="The ECCC city forecast snapshot is invalid",
        ) from exc
    encoded = json.dumps(
        frame,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    etag_source = content + b"\0" + frame["validTime"].encode() + b"\0" + (province or "").encode()
    etag = f'"{hashlib.sha256(etag_source).hexdigest()}"'
    headers = {
        "Cache-Control": "public, max-age=300, must-revalidate",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
        "X-Forecast-Source": "ECCC City Page Weather",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(encoded, media_type="application/geo+json", headers=headers)


async def _regional_outlooks(now: datetime) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            regional_outlooks,
            settings.data_root / CITY_FORECAST_SNAPSHOT,
            now,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, "No regional forecasts have been collected yet") from exc
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(503, "The regional forecast snapshot is invalid") from exc


@app.get("/api/v1/forecast/regions", tags=["forecast"])
async def forecast_regions() -> JSONResponse:
    return JSONResponse(
        await _regional_outlooks(datetime.now(UTC)),
        headers={"Cache-Control": "public, max-age=300, must-revalidate"},
    )


@app.get("/api/v1/forecast/nearest", tags=["forecast"])
async def forecast_nearest(
    longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
) -> dict[str, Any]:
    outlooks = await _regional_outlooks(datetime.now(UTC))
    match = nearest_region(outlooks["regions"], longitude, latitude)
    if match is None:
        raise HTTPException(404, "No forecast-region representative point is within 200 km")
    return match


@app.get("/api/v1/forecast/hourly", tags=["forecast"])
async def forecast_hourly(
    request: Request,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    area_id: Annotated[str, Query(pattern=r"^[a-f0-9]{16}$")],
) -> JSONResponse:
    now = datetime.now(UTC)
    outlooks = await _regional_outlooks(now)
    region = next((r for r in outlooks["regions"] if r["id"] == area_id), None)
    if region is None:
        raise HTTPException(404, "Unknown forecast region")
    await _enforce_sample_rate_limit(request)
    identity = json.dumps(
        [
            area_id,
            region["latitude"],
            region["longitude"],
            now.strftime("%Y%m%d%H"),
        ]
    )
    prepared_response = await prepared_hourly(request, region, now)
    if prepared_response is not None:
        return JSONResponse(prepared_response)
    cache_key = "weather:v1:forecast:hourly:" + hashlib.sha256(identity.encode()).hexdigest()
    cache = getattr(request.app.state, "redis", None)
    if cache is not None:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return JSONResponse(json.loads(cached))
        except (RedisError, ValueError):
            logger.warning("hourly_forecast_cache_read_failed")
    try:
        async with asyncio.timeout(90):
            response = await hourly_outlook(repository, region, now, _resolve_and_sample)
    except TimeoutError as exc:
        raise HTTPException(503, "Hourly forecasts are taking too long to load; try again") from exc
    if cache is not None:
        try:
            await cache.setex(cache_key, 300, json.dumps(response, allow_nan=False))
        except RedisError:
            logger.warning("hourly_forecast_cache_write_failed")
    return JSONResponse(response)


@app.get("/api/v1/golf/outlook", tags=["forecast"])
async def golf_forecast(
    request: Request,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    local_date: date,
    tee_time: Annotated[str, Query(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")],
    time_zone: Annotated[str, Query(max_length=100)] = "America/Halifax",
    days: Annotated[int, Query(ge=1, le=7)] = 7,
    min_temperature_c: Annotated[float, Query(ge=-30, le=50, allow_inf_nan=False)] = 8,
    max_temperature_c: Annotated[float, Query(ge=-30, le=50, allow_inf_nan=False)] = 30,
    max_wind_kmh: Annotated[float, Query(ge=0, le=150, allow_inf_nan=False)] = 25,
    max_rain_mm: Annotated[float, Query(ge=0, le=100, allow_inf_nan=False)] = 1,
    max_pop_percent: Annotated[float, Query(ge=0, le=100, allow_inf_nan=False)] = 40,
) -> JSONResponse:
    now = datetime.now(UTC)
    try:
        zone = ZoneInfo(time_zone)
        limits = GolfLimits(
            minTemperatureC=min_temperature_c,
            maxTemperatureC=max_temperature_c,
            maxWindKmh=max_wind_kmh,
            maxRainMm=max_rain_mm,
            maxPopPercent=max_pop_percent,
        )
    except (ZoneInfoNotFoundError, ValueError, ValidationError) as exc:
        raise HTTPException(
            422, "Choose a valid time zone and an ordered temperature range"
        ) from exc
    if (
        not now.astimezone(zone).date()
        <= local_date
        <= now.astimezone(zone).date() + timedelta(days=6)
    ):
        raise HTTPException(422, "The first date must be today or within the next six days")
    windows = playing_windows(local_date, clock_time.fromisoformat(tee_time), zone, days)
    await _enforce_sample_rate_limit(request)
    # Weather sampling is cached independently of user tolerances; preferences
    # never trigger ETL and are not persisted by the server.
    identity = json.dumps(
        [
            longitude,
            latitude,
            local_date.isoformat(),
            tee_time,
            time_zone,
            days,
            now.strftime("%Y%m%d%H"),
        ]
    )
    key = "weather:v1:golf:point:" + hashlib.sha256(identity.encode()).hexdigest()
    cache = getattr(request.app.state, "redis", None)
    point = None
    if cache is not None:
        try:
            raw = await cache.get(key)
            if raw:
                point = json.loads(raw)
        except (RedisError, ValueError):
            logger.warning("golf_cache_read_failed")
    if point is None:
        try:
            async with asyncio.timeout(50):
                point = await collect_point(
                    repository, longitude, latitude, windows, now, _resolve_and_sample
                )
        except TimeoutError as exc:
            raise HTTPException(503, "Point forecasts are taking too long; try again") from exc
        if cache is not None:
            try:
                await cache.setex(key, 300, json.dumps(point, allow_nan=False))
            except RedisError:
                logger.warning("golf_cache_write_failed")
    try:
        regions = (await _regional_outlooks(now))["regions"]
    except HTTPException:
        # Point-model weather still works without a regional bulletin catalogue.
        regions = []
    result = golf_outlook(point, regions, longitude, latitude, zone, windows, limits, now)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@app.get("/api/v1/forecast/precipitation", tags=["forecast"])
async def forecast_precipitation(
    request: Request,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    area_id: Annotated[str, Query(pattern=r"^[a-f0-9]{16}$")],
) -> JSONResponse:
    now = datetime.now(UTC)
    outlooks = await _regional_outlooks(now)
    region = next((r for r in outlooks["regions"] if r["id"] == area_id), None)
    if region is None:
        raise HTTPException(404, "Unknown forecast region")
    await _enforce_sample_rate_limit(request)
    # Bind cached estimates to the exact bulletin and its remaining periods.
    identity = json.dumps(
        [
            area_id,
            region["latitude"],
            region["longitude"],
            region["issuedAt"],
            region["periods"],
            now.strftime("%Y%m%d%H"),
        ],
        sort_keys=True,
    )
    cache_key = "weather:v1:forecast:precipitation:" + hashlib.sha256(identity.encode()).hexdigest()
    cache = getattr(request.app.state, "redis", None)
    if cache is not None:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return JSONResponse(json.loads(cached))
        except (RedisError, ValueError):
            logger.warning("precipitation_forecast_cache_read_failed")
    try:
        async with asyncio.timeout(90):
            response = await precipitation_outlook(repository, region, now, _resolve_and_sample)
    except TimeoutError as exc:
        raise HTTPException(
            503,
            "Precipitation estimates are taking too long to load; try again",
        ) from exc
    if cache is not None:
        try:
            await cache.setex(cache_key, 300, json.dumps(response, allow_nan=False))
        except RedisError:
            logger.warning("precipitation_forecast_cache_write_failed")
    return JSONResponse(response)


@app.get("/api/v1/fire-events", tags=["wildfire"])
async def list_fire_events(
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    bbox: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    """Return reconciled fire events from the current immutable snapshot."""

    path = settings.data_root / "derived" / "smoke" / "fire-events" / "latest.json"
    if not path.is_file() or path.is_symlink():
        raise HTTPException(
            status_code=404, detail="No reconciled fire-event snapshot is available"
        )
    payload = await run_in_threadpool(lambda: json.loads(path.read_text(encoding="utf-8")))
    start_utc = _aware(start, "start") if start else None
    end_utc = _aware(end, "end") if end else None
    if start_utc and end_utc and end_utc < start_utc:
        raise HTTPException(status_code=422, detail="end must not precede start")
    bounds: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parsed = tuple(float(value) for value in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="bbox must contain four numbers") from exc
        if len(parsed) != 4 or not (
            -180 <= parsed[0] < parsed[2] <= 180 and -90 <= parsed[1] < parsed[3] <= 90
        ):
            raise HTTPException(status_code=422, detail="bbox is invalid")
        bounds = parsed
    events = []
    for event in payload.get("events", []):
        first = datetime.fromisoformat(event["first_observed_at"].replace("Z", "+00:00"))
        last = datetime.fromisoformat(event["last_observed_at"].replace("Z", "+00:00"))
        if start_utc and last < start_utc or end_utc and first > end_utc:
            continue
        if bounds and not (
            bounds[0] <= event["longitude"] <= bounds[2]
            and bounds[1] <= event["latitude"] <= bounds[3]
        ):
            continue
        events.append(
            event | {"model_eligible": has_supported_cffeps_fuel(event.get("fuel_types"))}
        )
    return {
        "schemaVersion": payload.get("schema_version"),
        "algorithmVersion": payload.get("algorithm_version"),
        "items": events,
    }


@app.get("/api/v1/fire-events/{event_id}", tags=["wildfire"])
async def get_fire_event(
    event_id: Annotated[str, ApiPath(pattern=r"^[0-9a-f]{24}$")],
) -> dict[str, Any]:
    collection = await list_fire_events(start=None, end=None, bbox=None)
    for event in collection["items"]:
        if event["event_id"] == event_id:
            return event
    raise HTTPException(status_code=404, detail="Fire event was not found")


@app.get("/api/v1/smoke/scenarios", tags=["smoke"])
async def list_smoke_scenarios(
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    rows = await repository.list_scenarios(limit)
    return {"items": [ScenarioSummary.model_validate(row) for row in rows]}


@app.get("/api/v1/smoke/scenarios/{scenario_id}", tags=["smoke"])
async def get_smoke_scenario(
    scenario_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> ScenarioSummary:
    return ScenarioSummary.model_validate(await repository.get_scenario(scenario_id))


@app.get("/api/v1/smoke/scenarios/{scenario_id}/revisions", tags=["smoke"])
async def list_smoke_revisions(
    scenario_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> dict[str, Any]:
    rows = await repository.list_revisions(scenario_id)
    return {"items": [RevisionSummary.model_validate(row) for row in rows]}


@app.get("/api/v1/smoke/runs/{run_id}", tags=["smoke"])
async def get_smoke_run(
    run_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> SimulationRunSummary:
    return SimulationRunSummary.model_validate(await repository.get_run(run_id))


@app.get("/api/v1/smoke/runs/{run_id}/artifacts", tags=["smoke"])
async def list_smoke_artifacts(
    run_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> dict[str, Any]:
    return {"items": await repository.list_artifacts(run_id)}


@app.get("/api/v1/smoke/runs/{run_id}/summary", tags=["smoke"])
async def get_smoke_summary(
    run_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> dict[str, Any]:
    row = await repository.get_run(run_id)
    return {
        "runId": row["id"],
        "status": row["status"],
        "metrics": row["metrics"],
        "warnings": row["warnings"],
        "gfsCycleTime": row["gfs_cycle_time"],
        "primaryEmissionsOnly": True,
    }


@app.post(
    "/api/v1/smoke/scenarios",
    status_code=201,
    tags=["smoke"],
    dependencies=[Depends(_require_simulation_writes)],
)
async def create_smoke_scenario(
    request: ScenarioCreate,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> dict[str, Any]:
    await _preflight_smoke_scenario(request.config)
    scenario, revision = await repository.create_scenario(
        request.name, request.description, request.config
    )
    return {
        "scenario": ScenarioSummary.model_validate(scenario),
        "revision": RevisionSummary.model_validate(revision),
    }


@app.post(
    "/api/v1/smoke/scenarios/{scenario_id}/revisions",
    status_code=201,
    tags=["smoke"],
    dependencies=[Depends(_require_simulation_writes)],
)
async def create_smoke_revision(
    scenario_id: UUID,
    request: RevisionCreate,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> RevisionSummary:
    await _preflight_smoke_scenario(request.config)
    return RevisionSummary.model_validate(
        await repository.create_revision(scenario_id, request.config)
    )


@app.post(
    "/api/v1/smoke/scenarios/{scenario_id}/runs",
    status_code=202,
    tags=["smoke"],
    dependencies=[Depends(_require_simulation_writes)],
)
async def submit_smoke_run(
    scenario_id: UUID,
    request: RunCreate,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> RunSubmission:
    revision = await repository.get_revision(scenario_id, request.revision_id)
    config = SmokeScenarioConfig.model_validate(revision["canonical_config"])
    admission = await _preflight_smoke_scenario(config)
    run, reused = await repository.create_run(
        scenario_id,
        request.revision_id,
        request.run_kind,
        settings.smoke_max_queued_runs,
    )
    estimate = admission.public_estimate()
    estimate.update(
        {
            "maximumRuntimeSeconds": settings.smoke_run_timeout_seconds,
            "maximumOutputBytes": settings.smoke_maximum_output_bytes,
        }
    )
    return RunSubmission(
        run_id=run["id"],
        status=run["status"],
        status_url=f"/api/v1/smoke/runs/{run['id']}",
        reused=reused,
        estimate=estimate,
    )


@app.post(
    "/api/v1/smoke/runs/{run_id}/cancel",
    tags=["smoke"],
    dependencies=[Depends(_require_simulation_writes)],
)
async def cancel_smoke_run(
    run_id: UUID,
    repository: Annotated[SimulationRepository, Depends(get_simulation_repository)],
) -> dict[str, Any]:
    return await repository.cancel_run(run_id)


@app.get("/health/ready", tags=["health"])
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, Any] = {}
    try:
        async with (
            request.app.state.database.pool.connection(timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                request.app.state.database.loader.load("health/weather_api_ready.sql")
            )
            row = await cursor.fetchone()
            checks["postgres"] = bool(row and next(iter(row.values())))
    except Exception as exc:  # readiness reports failures instead of crashing
        checks["postgres"] = False
        checks["postgres_error"] = type(exc).__name__

    client = getattr(request.app.state, "redis", None)
    try:
        checks["redis"] = bool(client and await client.ping())
    except Exception as exc:
        checks["redis"] = False
        checks["redis_error"] = type(exc).__name__

    checks["data_root"] = settings.data_root.is_dir()
    ready_state = all(checks.get(name) is True for name in ("postgres", "redis", "data_root"))
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={"status": "ready" if ready_state else "not_ready", "checks": checks},
    )


@app.get("/api/v1/products", response_model=ProductCollection, tags=["catalogue"])
async def list_products(
    repository: Annotated[CatalogueReader, Depends(get_repository)],
) -> ProductCollection:
    return ProductCollection(
        items=[ProductSummary.model_validate(row) for row in await repository.list_products()]
    )


@app.get("/api/v1/variables", response_model=VariableCollection, tags=["catalogue"])
async def list_variables(
    repository: Annotated[CatalogueReader, Depends(get_repository)],
) -> VariableCollection:
    return VariableCollection(
        items=[VariableSummary.model_validate(row) for row in await repository.list_variables()]
    )


@app.get(
    "/api/v1/products/{product_code}/domains",
    response_model=DomainCollection,
    tags=["catalogue"],
)
async def list_domains(
    product_code: Annotated[str, ApiPath(pattern=PUBLIC_CODE)],
    repository: Annotated[CatalogueReader, Depends(get_repository)],
) -> DomainCollection:
    rows = await repository.list_domains(product_code)
    return DomainCollection(items=[DomainSummary.model_validate(row) for row in rows])


@app.get(
    "/api/v1/products/{product_code}/fields",
    response_model=FieldCollection,
    tags=["catalogue"],
)
async def list_fields(
    product_code: Annotated[str, ApiPath(pattern=PUBLIC_CODE)],
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    run: Annotated[datetime | None, Query()] = None,
) -> FieldCollection:
    rows = await repository.list_fields(product_code, _aware(run, "run") if run else None)
    return FieldCollection(items=[FieldSummary.model_validate(row) for row in rows])


@app.get(
    "/api/v1/products/{product_code}/runs",
    response_model=RunCollection,
    tags=["catalogue"],
)
async def list_runs(
    product_code: Annotated[str, ApiPath(pattern=PUBLIC_CODE)],
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
    before: Annotated[datetime | None, Query()] = None,
    field: Annotated[str | None, Query(pattern=PUBLIC_CODE)] = None,
) -> RunCollection:
    rows = await repository.list_runs(
        product_code,
        limit + 1,
        _aware(before, "before") if before else None,
        field,
    )
    page = rows[:limit]
    next_cursor = page[-1]["run_time"].isoformat() if len(rows) > limit else None
    return RunCollection(
        items=[RunSummary.model_validate(row) for row in page],
        next_cursor=next_cursor,
    )


@app.get(
    "/api/v1/products/{product_code}/runs/{run_time}/times",
    response_model=TimeCollection,
    tags=["catalogue"],
)
async def list_times(
    product_code: Annotated[str, ApiPath(pattern=PUBLIC_CODE)],
    run_time: datetime,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    field: Annotated[str | None, Query(pattern=PUBLIC_CODE)] = None,
) -> TimeCollection:
    rows = await repository.list_times(
        product_code,
        _aware(run_time, "run_time"),
        field,
    )
    return TimeCollection(items=[TimeSummary.model_validate(row) for row in rows])


@app.get(
    "/api/v1/products/{product_code}/timeline",
    response_model=TimelineCollection,
    tags=["catalogue"],
)
async def list_timeline(
    product_code: Annotated[str, ApiPath(pattern=PUBLIC_CODE)],
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    domain: Annotated[str, Query(pattern=PUBLIC_CODE)],
    field: Annotated[str, Query(pattern=PUBLIC_CODE)],
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 1000,
) -> TimelineCollection:
    if (start is None) != (end is None):
        raise HTTPException(
            status_code=422,
            detail="start and end must be supplied together",
        )
    aware_start = _aware(start, "start") if start else None
    aware_end = _aware(end, "end") if end else None
    if aware_start is not None and aware_end is not None and aware_start >= aware_end:
        raise HTTPException(status_code=422, detail="start must be earlier than end")

    rows = await repository.list_timeline(
        product_code,
        domain,
        field,
        aware_start,
        aware_end,
        limit + 1,
    )
    return TimelineCollection(
        items=[TimelineFrameSummary.model_validate(row) for row in rows[:limit]],
        truncated=len(rows) > limit,
    )


@app.get("/api/v1/layers/resolve", response_model=ResolvedLayer, tags=["layers"])
async def resolve_layer(
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    product: Annotated[str, Query(pattern=PUBLIC_CODE)],
    domain: Annotated[str, Query(pattern=PUBLIC_CODE)],
    run: Annotated[datetime, Query()],
    field: Annotated[str, Query(pattern=PUBLIC_CODE)],
    valid_time: Annotated[datetime, Query()],
    style: Annotated[str, Query(pattern=PUBLIC_CODE)] = "default",
    image_format: Annotated[Literal["webp", "png"], Query(alias="format")] = "webp",
    minimum: Annotated[float | None, Query()] = None,
    maximum: Annotated[float | None, Query()] = None,
    opacity_cutoff: Annotated[float | None, Query()] = None,
) -> ResolvedLayer:
    if (minimum is None) != (maximum is None):
        raise HTTPException(
            status_code=422,
            detail="minimum and maximum must be supplied together",
        )
    if minimum is not None and maximum is not None:
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise HTTPException(status_code=422, detail="display range must be finite")
        if minimum >= maximum:
            raise HTTPException(
                status_code=422,
                detail="minimum must be lower than maximum",
            )
    if opacity_cutoff is not None and not math.isfinite(opacity_cutoff):
        raise HTTPException(status_code=422, detail="opacity_cutoff must be finite")
    asset = await repository.resolve_asset(
        product=product,
        domain=domain,
        run_time=_aware(run, "run"),
        field=field,
        valid_time=_aware(valid_time, "valid_time"),
        style=style,
    )
    display_minimum = asset.display_min if minimum is None else minimum
    display_maximum = asset.display_max if maximum is None else maximum
    palette_mode = "relative" if asset.variable == "air_temperature" else "absolute"
    if minimum is None and palette_mode == "relative":
        data_range = rounded_temperature_range(asset.data_min, asset.data_max)
        if data_range is not None:
            display_minimum, display_maximum = data_range
    display_palette = palette_for_display(
        asset.palette_definition, display_minimum, display_maximum, palette_mode
    )
    now = int(time.time())
    token_expiry = (
        (now // settings.layer_token_ttl_seconds) + 1
    ) * settings.layer_token_ttl_seconds
    token = create_layer_token(
        LayerTokenPayload(
            asset_id=asset.asset_id,
            style_id=asset.style_id,
            asset_sha256=asset.asset_sha256,
            display_min=display_minimum,
            display_max=display_maximum,
            output_format=image_format,
            expires_at=token_expiry,
            opacity_cutoff=opacity_cutoff,
            palette_mode=palette_mode,
        ),
        settings.layer_token_secret,
    )
    return ResolvedLayer(
        product=asset.product,
        domain=asset.domain,
        run_time=asset.run_time,
        valid_time=asset.valid_time,
        forecast_hour=asset.forecast_hour,
        field=asset.field,
        variable=asset.variable,
        level=asset.level,
        unit=asset.unit,
        tile_url=f"/tiles/v1/{token}/{{z}}/{{x}}/{{y}}.{image_format}",
        token=token,
        bounds=asset.bounds,
        legend=Legend(
            minimum=display_minimum,
            maximum=display_maximum,
            palette=_palette_stops(display_palette),
        ),
    )


def _sample_asset(path: Path, longitude: float, latitude: float) -> tuple[float | None, bool]:
    try:
        with COGReader(path) as reader:
            point = reader.point(longitude, latitude)
    except PointOutsideBounds:
        return None, True
    value = point.array[0]
    if np.ma.is_masked(value) or not np.isfinite(value):
        return None, True
    return float(value), False


async def _resolve_and_sample(
    repository: CatalogueReader,
    *,
    product: str,
    domain: str,
    run_time: datetime,
    valid_time: datetime,
    field: str,
    longitude: float,
    latitude: float,
) -> SampleValue:
    asset = await repository.resolve_asset(
        product=product,
        domain=domain,
        run_time=run_time,
        field=field,
        valid_time=valid_time,
        style="default",
    )
    path = resolve_asset_path(settings.data_root, asset.relative_path)
    value, nodata = await run_in_threadpool(_sample_asset, path, longitude, latitude)
    return SampleValue(
        field=asset.field,
        variable=asset.variable,
        level=asset.level,
        value=value,
        unit=asset.unit,
        nodata=nodata,
    )


def _request_client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
    candidate = forwarded or (request.client.host if request.client else "unknown")
    try:
        normalized = str(ipaddress.ip_address(candidate))
    except ValueError:
        normalized = "unknown"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


async def _enforce_sample_rate_limit(request: Request) -> None:
    client = getattr(request.app.state, "redis", None)
    if client is None:
        return
    window = int(time.time()) // 60
    key = f"weather:v1:rate:sample:{window}:{_request_client_key(request)}"
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 61)
    except RedisError:
        logger.warning("sample_rate_limit_unavailable")
        return
    if count > settings.sample_rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Point-sampling rate limit exceeded",
            headers={"Retry-After": "60"},
        )


def _sample_cache_key(
    *,
    product: str,
    domain: str,
    run_time: datetime,
    valid_time: datetime,
    longitude: float,
    latitude: float,
    fields: tuple[str, ...],
) -> str:
    identity = json.dumps(
        {
            "product": product,
            "domain": domain,
            "run": run_time.isoformat(),
            "valid": valid_time.isoformat(),
            "longitude": round(longitude, 6),
            "latitude": round(latitude, 6),
            "fields": fields,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return "weather:v1:sample:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _wind_vector_cache_key(
    *,
    product: str,
    domain: str,
    run_time: datetime,
    valid_time: datetime,
    bbox: tuple[float, float, float, float],
    columns: int,
    rows: int,
) -> str:
    identity = json.dumps(
        {
            "product": product,
            "domain": domain,
            "run": run_time.isoformat(),
            "valid": valid_time.isoformat(),
            "bbox": list(bbox),
            "columns": columns,
            "rows": rows,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return "weather:v1:wind:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _wind_grid_points(
    bbox: tuple[float, float, float, float],
    columns: int,
    rows: int,
) -> list[tuple[float, float]]:
    west, south, east, north = bbox
    longitude_step = (east - west) / columns
    latitude_step = (north - south) / rows
    return [
        (
            west + (column + 0.5) * longitude_step,
            north - (row + 0.5) * latitude_step,
        )
        for row in range(rows)
        for column in range(columns)
    ]


def _sample_raster_points(
    path: Path,
    points: list[tuple[float, float]],
) -> list[float | None]:
    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError("Wind asset is missing a coordinate reference system")
        transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        projected = [transformer.transform(longitude, latitude) for longitude, latitude in points]
        values: list[float | None] = []
        for sample in dataset.sample(projected, indexes=1, masked=True):
            value = sample[0]
            values.append(
                None if np.ma.is_masked(value) or not np.isfinite(value) else float(value)
            )
        return values


def _read_wind_vectors(
    u_path: Path,
    v_path: Path,
    bbox: tuple[float, float, float, float],
    columns: int,
    rows: int,
) -> list[WindVectorFeature]:
    points = _wind_grid_points(bbox, columns, rows)
    u_values = _sample_raster_points(u_path, points)
    v_values = _sample_raster_points(v_path, points)
    features: list[WindVectorFeature] = []
    for (longitude, latitude), u_value, v_value in zip(points, u_values, v_values, strict=True):
        if u_value is None or v_value is None:
            continue
        speed = math.hypot(u_value, v_value)
        bearing = round(math.degrees(math.atan2(u_value, v_value)) % 360, 1) % 360
        features.append(
            WindVectorFeature(
                geometry=WindVectorGeometry(coordinates=(round(longitude, 6), round(latitude, 6))),
                properties=WindVectorProperties(
                    u=round(u_value, 3),
                    v=round(v_value, 3),
                    speed=round(speed, 3),
                    bearing=bearing,
                ),
            )
        )
    return features


@app.get(
    "/api/v1/wind-vectors",
    response_model=WindVectorCollection,
    tags=["layers"],
)
async def wind_vectors(
    request: Request,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    product: Annotated[str, Query(pattern=PUBLIC_CODE)],
    domain: Annotated[str, Query(pattern=PUBLIC_CODE)],
    run: Annotated[datetime, Query()],
    valid_time: Annotated[datetime, Query()],
    west: Annotated[float, Query(ge=-180, le=180)],
    south: Annotated[float, Query(ge=-90, le=90)],
    east: Annotated[float, Query(ge=-180, le=180)],
    north: Annotated[float, Query(ge=-90, le=90)],
    columns: Annotated[int, Query(ge=4, le=30)] = 18,
    rows: Annotated[int, Query(ge=3, le=20)] = 10,
) -> WindVectorCollection:
    if west >= east or south >= north:
        raise HTTPException(
            status_code=422,
            detail="Wind-vector bounds must have west < east and south < north",
        )
    run_time = _aware(run, "run")
    requested_valid_time = _aware(valid_time, "valid_time")
    bbox = (west, south, east, north)
    await _enforce_sample_rate_limit(request)
    cache = getattr(request.app.state, "redis", None)
    cache_key = _wind_vector_cache_key(
        product=product,
        domain=domain,
        run_time=run_time,
        valid_time=requested_valid_time,
        bbox=bbox,
        columns=columns,
        rows=rows,
    )
    if cache is not None and settings.sample_cache_ttl_seconds:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return WindVectorCollection.model_validate_json(cached)
        except (RedisError, ValueError):
            logger.warning("wind_vector_cache_read_failed")

    u_asset, v_asset = await asyncio.gather(
        repository.resolve_asset(
            product=product,
            domain=domain,
            run_time=run_time,
            field=WIND_U_FIELD,
            valid_time=requested_valid_time,
            style="default",
        ),
        repository.resolve_asset(
            product=product,
            domain=domain,
            run_time=run_time,
            field=WIND_V_FIELD,
            valid_time=requested_valid_time,
            style="default",
        ),
    )
    if u_asset.variable != "wind_u" or v_asset.variable != "wind_v":
        raise HTTPException(status_code=500, detail="Registered wind components are invalid")
    if u_asset.unit != v_asset.unit:
        raise HTTPException(status_code=500, detail="Wind component units do not match")

    with OPERATION_DURATION.labels("weather-api", "wind_vector_grid").time():
        features = await run_in_threadpool(
            _read_wind_vectors,
            resolve_asset_path(settings.data_root, u_asset.relative_path),
            resolve_asset_path(settings.data_root, v_asset.relative_path),
            bbox,
            columns,
            rows,
        )
    response = WindVectorCollection(
        product=product,
        domain=domain,
        run_time=run_time,
        valid_time=requested_valid_time,
        unit=u_asset.unit,
        bbox=bbox,
        columns=columns,
        rows=rows,
        feature_count=len(features),
        features=features,
    )
    if cache is not None and settings.sample_cache_ttl_seconds:
        try:
            await cache.setex(
                cache_key,
                settings.sample_cache_ttl_seconds,
                response.model_dump_json(by_alias=True),
            )
        except RedisError:
            logger.warning("wind_vector_cache_write_failed")
    return response


@app.get("/api/v1/sample", response_model=SampleResponse, tags=["layers"])
async def sample(
    request: Request,
    repository: Annotated[CatalogueReader, Depends(get_repository)],
    product: Annotated[str, Query(pattern=PUBLIC_CODE)],
    domain: Annotated[str, Query(pattern=PUBLIC_CODE)],
    run: Annotated[datetime, Query()],
    valid_time: Annotated[datetime, Query()],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    field: Annotated[list[str], Query(min_length=1, max_length=10)],
) -> SampleResponse:
    if any(not re.fullmatch(PUBLIC_CODE, item) for item in field):
        raise HTTPException(status_code=422, detail="One or more field codes are invalid")
    run_time = _aware(run, "run")
    requested_valid_time = _aware(valid_time, "valid_time")
    requested_fields = tuple(dict.fromkeys(field))
    await _enforce_sample_rate_limit(request)
    cache = getattr(request.app.state, "redis", None)
    cache_key = _sample_cache_key(
        product=product,
        domain=domain,
        run_time=run_time,
        valid_time=requested_valid_time,
        longitude=longitude,
        latitude=latitude,
        fields=requested_fields,
    )
    if cache is not None and settings.sample_cache_ttl_seconds:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return SampleResponse.model_validate_json(cached)
        except (RedisError, ValueError):
            logger.warning("sample_cache_read_failed")
    with OPERATION_DURATION.labels("weather-api", "point_sample").time():
        values = await asyncio.gather(
            *(
                _resolve_and_sample(
                    repository,
                    product=product,
                    domain=domain,
                    run_time=run_time,
                    valid_time=requested_valid_time,
                    field=item,
                    longitude=longitude,
                    latitude=latitude,
                )
                for item in requested_fields
            )
        )
    response = SampleResponse(
        longitude=longitude,
        latitude=latitude,
        run_time=run_time,
        valid_time=requested_valid_time,
        values=values,
    )
    if cache is not None and settings.sample_cache_ttl_seconds:
        try:
            await cache.setex(
                cache_key,
                settings.sample_cache_ttl_seconds,
                response.model_dump_json(by_alias=True),
            )
        except RedisError:
            logger.warning("sample_cache_write_failed")
    return response


@app.get(
    "/api/v1/status/ingestion",
    response_model=IngestionStatusCollection,
    tags=["status"],
)
async def ingestion_status(
    repository: Annotated[CatalogueReader, Depends(get_repository)],
) -> IngestionStatusCollection:
    rows = await repository.list_ingestion_status()
    return IngestionStatusCollection(items=[IngestionStatus.model_validate(row) for row in rows])
