"""Handwritten-SQL catalogue repository used by the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from psycopg_pool import AsyncConnectionPool
from weather_common.db import SqlFileLoader


class CatalogueNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedAssetRecord:
    asset_id: int
    relative_path: str
    style_id: int
    asset_sha256: str
    product: str
    domain: str
    run_time: datetime
    valid_time: datetime
    forecast_hour: int | None
    field: str
    variable: str
    level: str
    unit: str
    bounds: tuple[float, float, float, float] | None
    palette_definition: dict[str, Any]
    display_min: float
    display_max: float
    data_min: float | None = None
    data_max: float | None = None


class CatalogueReader(Protocol):
    async def list_products(self) -> list[dict[str, Any]]: ...

    async def list_variables(self) -> list[dict[str, Any]]: ...

    async def list_domains(self, product: str) -> list[dict[str, Any]]: ...

    async def list_fields(
        self, product: str, run_time: datetime | None = None
    ) -> list[dict[str, Any]]: ...

    async def list_runs(
        self,
        product: str,
        limit: int,
        before: datetime | None = None,
        field: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def list_times(
        self,
        product: str,
        run_time: datetime,
        field: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def list_timeline(
        self,
        product: str,
        domain: str,
        field: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    async def list_ingestion_status(self) -> list[dict[str, Any]]: ...

    async def resolve_asset(
        self,
        *,
        product: str,
        domain: str,
        run_time: datetime,
        field: str,
        valid_time: datetime,
        style: str,
    ) -> ResolvedAssetRecord: ...


class PostgresCatalogueRepository:
    def __init__(self, pool: AsyncConnectionPool, sql: SqlFileLoader) -> None:
        self.pool = pool
        self.sql = sql

    async def _fetch_all(self, query_name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        async with self.pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(self.sql.load(query_name), parameters)
            return list(await cursor.fetchall())

    async def _fetch_one(self, query_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        rows = await self._fetch_all(query_name, parameters)
        if not rows:
            raise CatalogueNotFoundError
        return rows[0]

    async def list_products(self) -> list[dict[str, Any]]:
        return await self._fetch_all("catalogue/list_products.sql", {})

    async def list_variables(self) -> list[dict[str, Any]]:
        return await self._fetch_all("catalogue/list_variables.sql", {})

    async def list_domains(self, product: str) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "catalogue/list_domains_for_product.sql", {"product_code": product}
        )

    async def list_fields(
        self, product: str, run_time: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "catalogue/list_fields_for_product.sql",
            {"product_code": product, "run_time": run_time},
        )

    async def list_runs(
        self,
        product: str,
        limit: int,
        before: datetime | None = None,
        field: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "catalogue/list_runs_for_product.sql",
            {
                "product_code": product,
                "field_code": field,
                "before": before,
                "limit": limit,
            },
        )

    async def list_times(
        self,
        product: str,
        run_time: datetime,
        field: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "catalogue/list_times_for_run.sql",
            {
                "product_code": product,
                "run_time": run_time,
                "field_code": field,
            },
        )

    async def list_timeline(
        self,
        product: str,
        domain: str,
        field: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "catalogue/list_best_timeline.sql",
            {
                "product_code": product,
                "domain_code": domain,
                "field_code": field,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
            },
        )

    async def list_ingestion_status(self) -> list[dict[str, Any]]:
        return await self._fetch_all("catalogue/list_ingestion_status.sql", {})

    async def resolve_asset(
        self,
        *,
        product: str,
        domain: str,
        run_time: datetime,
        field: str,
        valid_time: datetime,
        style: str,
    ) -> ResolvedAssetRecord:
        row = await self._fetch_one(
            "assets/resolve_cog_asset.sql",
            {
                "product_code": product,
                "domain_code": domain,
                "run_time": run_time,
                "field_code": field,
                "valid_time": valid_time,
                "style_code": style,
            },
        )
        return ResolvedAssetRecord(
            asset_id=row["asset_id"],
            relative_path=row["relative_path"],
            style_id=row["style_id"],
            asset_sha256=row["asset_sha256"],
            product=row["product"],
            domain=row["domain"],
            run_time=row["run_time"],
            valid_time=row["valid_time"],
            forecast_hour=row["forecast_hour"],
            field=row["field"],
            variable=row["variable"],
            level=row["level"],
            unit=row["unit"],
            bounds=tuple(row["bounds"]) if row["bounds"] is not None else None,
            palette_definition=row["palette_definition"],
            display_min=float(row["display_min"]),
            display_max=float(row["display_max"]),
            data_min=float(row["data_min"]) if row["data_min"] is not None else None,
            data_max=float(row["data_max"]) if row["data_max"] is not None else None,
        )
