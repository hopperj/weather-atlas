"""Token-restricted raster tile service for catalogue-registered local COGs."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse, Response
from rio_tiler.errors import TileOutsideBounds
from starlette.concurrency import run_in_threadpool
from weather_common import __version__
from weather_common.db import Database, SqlFileLoader
from weather_common.layer_tokens import LayerTokenError, verify_layer_token
from weather_common.metrics import OPERATION_DURATION, observe_http_request, prometheus_response
from weather_common.settings import Settings

from weather_tiles.rendering import (
    TileRenderingError,
    render_registered_tile,
    resolve_asset_path,
)
from weather_tiles.repository import PostgresTileAssetRepository, TileAssetReader

settings = Settings.from_environment()
logger = logging.getLogger("weather_tiles")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    database = Database(
        settings.database_url,
        min_size=1,
        max_size=12,
        loader=SqlFileLoader(settings.sql_root),
    )
    await database.open()
    application.state.database = database
    try:
        yield
    finally:
        await database.close()


app = FastAPI(
    title="Weather Platform Tile API",
    version=__version__,
    description="Token-restricted raster tile rendering for registered weather assets.",
    lifespan=lifespan,
)

# The same read-only imagery routes use this service's catalogue role and local data mount.
from weather_api.imagery import router as imagery_router  # noqa: E402

app.include_router(imagery_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))[:128]
    started = time.perf_counter()
    status = 500
    try:
        response = await observe_http_request("tile-api", request, call_next)
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


def get_repository(request: Request) -> TileAssetReader:
    override = getattr(request.app.state, "tile_repository", None)
    if override is not None:
        return override
    try:
        database = request.app.state.database
        return PostgresTileAssetRepository(database.pool, database.loader)
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="Tile catalogue is not ready") from exc


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok", "service": "tile-api", "version": __version__}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return prometheus_response()


@app.get("/health/ready", tags=["health"])
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, Any] = {"data_root": settings.data_root.is_dir()}
    try:
        async with (
            request.app.state.database.pool.connection(timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                request.app.state.database.loader.load("health/tile_api_ready.sql")
            )
            row = await cursor.fetchone()
            checks["postgres"] = bool(row and next(iter(row.values())))
    except Exception as exc:
        checks["postgres"] = False
        checks["postgres_error"] = type(exc).__name__
    ready_state = checks["data_root"] is True and checks["postgres"] is True
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={"status": "ready" if ready_state else "not_ready", "checks": checks},
    )


@app.get("/tiles/v1/{layer_token}/{z}/{x}/{y}.{image_format}", tags=["tiles"])
async def tile(
    request: Request,
    layer_token: str = Path(pattern=r"^[A-Za-z0-9_.-]{20,1024}$"),
    z: int = Path(ge=0, le=22),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
    image_format: str = Path(pattern=r"^(png|webp)$"),
) -> Response:
    try:
        payload = verify_layer_token(layer_token, settings.layer_token_secret)
    except LayerTokenError as exc:
        raise HTTPException(status_code=404, detail="Unknown or expired layer token") from exc
    if payload.output_format != image_format:
        raise HTTPException(status_code=404, detail="Layer token does not permit this format")
    if x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=404, detail="Tile coordinate is outside its zoom matrix")

    repository = get_repository(request)
    asset = await repository.get_renderable_asset(
        asset_id=payload.asset_id,
        style_id=payload.style_id,
        asset_sha256=payload.asset_sha256,
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Registered layer asset is unavailable")

    try:
        path = resolve_asset_path(settings.data_root, asset.relative_path)
        with OPERATION_DURATION.labels("tile-api", "render_tile").time():
            body = await run_in_threadpool(
                render_registered_tile,
                path,
                x=x,
                y=y,
                z=z,
                display_min=payload.display_min,
                display_max=payload.display_max,
                opacity_cutoff=payload.opacity_cutoff,
                palette_mode=payload.palette_mode,
                palette_definition=asset.palette_definition,
                image_format=image_format,
                resampling_method=asset.resampling_method,
            )
    except (FileNotFoundError, TileOutsideBounds) as exc:
        raise HTTPException(status_code=404, detail="Tile is outside the available asset") from exc
    except TileRenderingError as exc:
        raise HTTPException(status_code=422, detail="Registered layer style is invalid") from exc

    remaining = max(0, payload.expires_at - int(time.time()))
    etag = hashlib.sha256(layer_token.encode("ascii")).hexdigest()
    return Response(
        content=body,
        media_type=f"image/{image_format}",
        headers={
            "Cache-Control": f"public, max-age={remaining}, immutable",
            "ETag": f'"{etag}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
