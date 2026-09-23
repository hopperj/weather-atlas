"""Synchronous ingestion catalogue writes using reviewed SQL files."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from weather_common.db import SqlFileLoader

from weather_ingest.config import ProductConfig
from weather_ingest.models import ParsedSourceObject, RemoteRun
from weather_ingest.storage import canonical_source_key


class IngestionCatalogueError(RuntimeError):
    pass


class IngestionCatalogue:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        loader: SqlFileLoader | None = None,
    ) -> None:
        self.database_url = database_url or os.environ["WEATHER_DATABASE_URL"]
        self.loader = loader or SqlFileLoader()

    @staticmethod
    def _one(cursor, label: str) -> dict[str, Any]:
        row = cursor.fetchone()
        if row is None:
            raise IngestionCatalogueError(f"catalogue operation returned no row: {label}")
        return row

    def register_manifest(
        self,
        config: ProductConfig,
        run: RemoteRun,
        parsed_objects: Iterable[ParsedSourceObject],
        *,
        source: str = "manual_inventory",
    ) -> tuple[int, dict[str, int]]:
        objects = list(parsed_objects)
        manifest = {
            "source": source,
            "object_count": len(objects),
            "required_fields": list(config.visibility.required_field_codes),
            "product_kind": config.kind,
            "reference_time_semantics": (
                "initialization_time" if config.kind == "forecast" else "valid_time"
            ),
            "requested_at": datetime.now(UTC).isoformat(),
        }
        expected_count = config.expected_processing_asset_count(
            reference_hour=run.initialization_time.hour
        )
        source_ids: dict[str, int] = {}
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            run_cursor = connection.execute(
                self.loader.load("ingestion/upsert_product_run.sql"),
                {
                    "product_code": run.product_code,
                    "domain_code": run.domain_code,
                    "run_time": run.initialization_time,
                    "source_status": "discovered",
                    "processing_status": "processing",
                    "source_manifest": Jsonb(manifest),
                    "expected_asset_count": expected_count,
                    "discovered_asset_count": len(objects),
                },
            )
            run_row = self._one(run_cursor, "upsert product run")
            for parsed in objects:
                canonical_key = canonical_source_key(parsed)
                source_cursor = connection.execute(
                    self.loader.load("ingestion/upsert_source_object.sql"),
                    {
                        "provider_code": config.provider,
                        "product_code": config.code,
                        "product_run_id": run_row["id"],
                        "canonical_key": canonical_key,
                        "observed_url": parsed.remote.url,
                        "observed_aliases": Jsonb([]),
                        "response_headers": Jsonb(
                            {
                                "listing_size_is_exact": parsed.remote.size_is_exact,
                                "listing_etag": parsed.remote.etag,
                            }
                        ),
                        "reported_size_bytes": parsed.remote.size_bytes,
                    },
                )
                source_row = self._one(source_cursor, "upsert source object")
                source_ids[parsed.remote.filename] = source_row["id"]
        return run_row["id"], source_ids

    def source_object_for_processing(self, source_object_id: int) -> dict[str, Any]:
        """Resolve one registered source object for an ID-only mapped task."""

        return self._execute_one(
            "ingestion/get_source_object_for_processing.sql",
            {"source_object_id": source_object_id},
            "resolve source object for processing",
        )

    def available_asset_conversions(self, product_run_ids: Iterable[int]) -> dict[str, str]:
        """Return processed paths and conversion versions for selected runs."""

        run_ids = list(product_run_ids)
        if not run_ids:
            return {}
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            cursor = connection.execute(
                self.loader.load("ingestion/list_available_assets.sql"),
                {"product_run_ids": run_ids},
            )
            return {
                str(row["relative_path"]): str(row["conversion_key"] or "")
                for row in cursor.fetchall()
            }

    def available_processing_slots(
        self,
        product_code: str,
        domain_code: str,
        run_times: Iterable[datetime],
    ) -> dict[tuple[datetime, str, int], tuple[str, str]]:
        """Return already published field/hour slots for automatic discovery."""

        values = list(run_times)
        if not values:
            return {}
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            cursor = connection.execute(
                self.loader.load("ingestion/list_available_processing_slots.sql"),
                {
                    "product_code": product_code,
                    "domain_code": domain_code,
                    "run_times": values,
                },
            )
            return {
                (
                    row["run_time"].astimezone(UTC),
                    str(row["field_code"]),
                    int(row["forecast_hour"]),
                ): (
                    str(row["relative_path"]),
                    str(row["conversion_key"] or ""),
                )
                for row in cursor.fetchall()
            }

    def recover_source_requests(
        self,
        product_code: str,
        *,
        limit: int,
    ) -> list[dict[str, int]]:
        """Revive and return registered sources that never produced an asset."""

        if limit < 1:
            return []
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            cursor = connection.execute(
                self.loader.load("ingestion/recover_source_objects.sql"),
                {
                    "product_code": product_code,
                    "limit": limit,
                },
            )
            return [
                {
                    "product_run_id": int(row["product_run_id"]),
                    "source_object_id": int(row["source_object_id"]),
                }
                for row in cursor.fetchall()
            ]

    def begin_download(self, source_object_id: int) -> None:
        self._execute_one(
            "ingestion/begin_source_download.sql",
            {"source_object_id": source_object_id},
            "begin source download",
        )

    def mark_downloaded(
        self,
        source_object_id: int,
        *,
        relative_path: str,
        size_bytes: int,
        sha256: str,
    ) -> None:
        self._execute_one(
            "ingestion/mark_source_downloaded.sql",
            {
                "source_object_id": source_object_id,
                "local_raw_path": relative_path,
                "actual_size_bytes": size_bytes,
                "sha256": sha256,
                "downloaded_at": datetime.now(UTC),
            },
            "mark source downloaded",
        )

    def mark_source_failed(self, source_object_id: int, error: Exception) -> None:
        self._execute_one(
            "ingestion/mark_source_failed.sql",
            {
                "source_object_id": source_object_id,
                "error_class": type(error).__name__,
                "error_message": str(error)[:2000],
                "error_detail": Jsonb({}),
            },
            "mark source failed",
        )

    def register_asset(
        self,
        *,
        product_run_id: int,
        parsed: ParsedSourceObject,
        field_code: str,
        relative_path: str,
        file_size_bytes: int,
        sha256: str,
        projection: str,
        bounds: tuple[float, float, float, float],
        width: int,
        height: int,
        band_count: int,
        nodata_value: float | None,
        minimum_value: float | None,
        maximum_value: float | None,
        source_sha256: str,
        conversion_key: str,
    ) -> int:
        minimum_x, minimum_y, maximum_x, maximum_y = bounds
        bounds_wkt = (
            f"POLYGON(({minimum_x} {minimum_y}, {maximum_x} {minimum_y}, "
            f"{maximum_x} {maximum_y}, {minimum_x} {maximum_y}, "
            f"{minimum_x} {minimum_y}))"
        )
        if parsed.time_kind == "forecast":
            forecast_hour: int | None = parsed.forecast_hour
            interval_start = None
            interval_end = None
            time_kind = "instant"
        else:
            if parsed.interval_start is None or parsed.interval_end is None:
                raise IngestionCatalogueError(
                    "analysis assets require an explicit accumulation interval"
                )
            forecast_hour = None
            interval_start = parsed.interval_start
            interval_end = parsed.interval_end
            time_kind = "accumulation"
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            time_cursor = connection.execute(
                self.loader.load("ingestion/upsert_product_time.sql"),
                {
                    "product_run_id": product_run_id,
                    "valid_time": parsed.valid_time,
                    "forecast_hour": forecast_hour,
                    "interval_start": interval_start,
                    "interval_end": interval_end,
                    "time_kind": time_kind,
                },
            )
            product_time = self._one(time_cursor, "upsert product time")
            field_cursor = connection.execute(
                self.loader.load("ingestion/resolve_product_field.sql"),
                {"product_code": parsed.product_code, "field_code": field_code},
            )
            field = self._one(field_cursor, "resolve product field")
            asset_cursor = connection.execute(
                self.loader.load("ingestion/upsert_asset.sql"),
                {
                    "product_id": field["product_id"],
                    "product_run_id": product_run_id,
                    "product_time_id": product_time["id"],
                    "product_field_id": field["product_field_id"],
                    "vertical_level_id": field["vertical_level_id"],
                    "asset_role": "processed_cog",
                    "relative_path": relative_path,
                    "mime_type": "image/tiff; application=geotiff; profile=cloud-optimized",
                    "file_size_bytes": file_size_bytes,
                    "sha256": sha256,
                    "projection": projection,
                    "bounds_wkt": bounds_wkt,
                    "width": width,
                    "height": height,
                    "band_count": band_count,
                    "nodata_value": nodata_value,
                    "minimum_value": minimum_value,
                    "maximum_value": maximum_value,
                    "statistics": Jsonb(
                        {"minimum": minimum_value, "maximum": maximum_value}
                    ),
                    "provenance": Jsonb(
                        {
                            "source_sha256": source_sha256,
                            "conversion": field_code,
                            "conversion_key": conversion_key,
                            "source_time_kind": parsed.time_kind,
                            "analysis_revision": parsed.analysis_revision,
                            "accumulation_hours": parsed.accumulation_hours,
                        }
                    ),
                    "status": "available",
                },
            )
            asset = self._one(asset_cursor, "upsert processed asset")
        return asset["id"]

    def finalize_run(self, product_run_id: int, required_field_codes: tuple[str, ...]) -> dict:
        return self._execute_one(
            "ingestion/finalize_product_run.sql",
            {
                "product_run_id": product_run_id,
                "required_field_codes": list(required_field_codes),
            },
            "finalize product run",
        )

    def _execute_one(
        self, query_name: str, parameters: dict[str, Any], label: str
    ) -> dict[str, Any]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            cursor = connection.execute(self.loader.load(query_name), parameters)
            return self._one(cursor, label)
