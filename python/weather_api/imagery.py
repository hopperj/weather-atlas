"""Read-only observation catalogue and local RGB tile serving. No upstream network calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as ApiPath
from fastapi.responses import Response
from psycopg.errors import UndefinedTable
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import COGReader
from rio_tiler.utils import render
from starlette.concurrency import run_in_threadpool
from weather_common.settings import Settings
from weather_tiles.rendering import resolve_asset_path

router = APIRouter()
settings = Settings.from_environment()


class ImageryRepository:
    def __init__(self, database):
        self.database = database

    async def rows(self, query: str, parameters: dict | None = None) -> list[dict]:
        try:
            async with self.database.pool.connection() as connection:
                cursor = await connection.execute(
                    self.database.loader.load(f"imagery/{query}.sql"), parameters
                )
                return list(await cursor.fetchall())
        except UndefinedTable as error:
            raise HTTPException(503, "Imagery catalogue is not installed on this server") from error

    async def products(self) -> list[dict]:
        return await self.rows("products")

    async def timeline(self, code: str) -> list[dict]:
        return await self.rows("timeline", {"code": code})

    async def frame(self, frame_id: UUID) -> dict | None:
        rows = await self.rows("frame", {"id": frame_id})
        return rows[0] if rows else None


def repository(request: Request):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(503, "Imagery catalogue is not ready")
    return ImageryRepository(database)


@router.get("/api/v1/imagery", tags=["imagery"])
async def catalogue(repo: Annotated[ImageryRepository, Depends(repository)]):
    now = datetime.now(UTC)
    items = []
    for product in await repo.products():
        frames = sorted(await repo.timeline(product["code"]), key=lambda frame: frame["valid_time"])
        items.append(
            {
                "code": product["code"],
                "name": product["name"],
                "kind": product["kind"],
                "attribution": product["attribution"],
                "stale": not frames or now - frames[-1]["valid_time"] > timedelta(minutes=30),
                "frames": [
                    {
                        "id": str(frame["id"]),
                        "validTime": frame["valid_time"],
                        "bounds": frame["bounds"],
                        "tileUrl": f"/tiles/imagery/{frame['id']}/{{z}}/{{x}}/{{y}}.png",
                        "legendUrl": f"/tiles/imagery/{frame['id']}/legend.png",
                    }
                    for frame in frames
                ],
            }
        )
    return {"items": items}


def render_imagery(path: Path, z: int, x: int, y: int) -> bytes:
    try:
        with COGReader(path) as source:
            image = source.tile(x, y, z, tilesize=256, indexes=(1, 2, 3))
        return image.render(img_format="PNG")
    except TileOutsideBounds:
        # Outside coverage is transparent; it must not look like a data fetch failure.
        return render(
            np.zeros((3, 256, 256), dtype="uint8"),
            mask=np.zeros((256, 256), dtype="uint8"),
            img_format="PNG",
        )


@router.get("/tiles/imagery/{frame_id}/{z}/{x}/{y}.png", tags=["imagery"])
async def imagery_tile(
    request: Request,
    frame_id: UUID,
    repo: Annotated[ImageryRepository, Depends(repository)],
    z: int = ApiPath(ge=0, le=22),
    x: int = ApiPath(ge=0),
    y: int = ApiPath(ge=0),
):
    if x >= 2**z or y >= 2**z:
        raise HTTPException(404, "Tile is outside its zoom matrix")
    frame = await repo.frame(frame_id)
    if frame is None:
        raise HTTPException(404, "Collected imagery frame is unavailable")
    etag = f'"{frame["content_sha256"]}-{z}-{x}-{y}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=86400, immutable"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        path = resolve_asset_path(settings.data_root, frame["relative_path"])
        body = await run_in_threadpool(render_imagery, path, z, x, y)
    except FileNotFoundError as error:
        raise HTTPException(404, "Collected imagery file is unavailable") from error
    return Response(body, media_type="image/png", headers=headers)


@router.get("/tiles/imagery/{frame_id}/legend.png", tags=["imagery"])
async def imagery_legend(frame_id: UUID, repo: Annotated[ImageryRepository, Depends(repository)]):
    frame = await repo.frame(frame_id)
    relative = frame["provenance"].get("legendPath") if frame else None
    if not relative:
        raise HTTPException(404, "No collected legend is available for this frame")
    try:
        path = resolve_asset_path(settings.data_root, relative)
        body = await run_in_threadpool(path.read_bytes)
    except FileNotFoundError as error:
        raise HTTPException(404, "Collected legend is unavailable") from error
    return Response(
        body, media_type="image/png", headers={"Cache-Control": "public, max-age=86400, immutable"}
    )
