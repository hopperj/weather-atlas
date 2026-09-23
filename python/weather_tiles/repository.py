"""SQL-backed resolver for token-bound raster assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from psycopg_pool import AsyncConnectionPool
from weather_common.db import SqlFileLoader


@dataclass(frozen=True, slots=True)
class RenderableAsset:
    asset_id: int
    relative_path: str
    asset_sha256: str
    style_id: int
    resampling_method: str
    palette_definition: dict[str, Any]


class TileAssetReader(Protocol):
    async def get_renderable_asset(
        self, *, asset_id: int, style_id: int, asset_sha256: str
    ) -> RenderableAsset | None: ...


class PostgresTileAssetRepository:
    def __init__(self, pool: AsyncConnectionPool, sql: SqlFileLoader) -> None:
        self.pool = pool
        self.sql = sql

    async def get_renderable_asset(
        self, *, asset_id: int, style_id: int, asset_sha256: str
    ) -> RenderableAsset | None:
        async with self.pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(
                self.sql.load("assets/get_renderable_asset_by_id.sql"),
                {
                    "asset_id": asset_id,
                    "style_id": style_id,
                    "asset_sha256": asset_sha256,
                },
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return RenderableAsset(
            asset_id=row["asset_id"],
            relative_path=row["relative_path"],
            asset_sha256=row["asset_sha256"],
            style_id=row["style_id"],
            resampling_method=row["resampling_method"],
            palette_definition=row["palette_definition"],
        )
