"""Classify a remote run and calculate bounded storage estimates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from weather_ingest.adapters.base import ProductSourceAdapter
from weather_ingest.models import (
    InventoryDisposition,
    InventoryObject,
    RemoteRun,
)


@dataclass(frozen=True, slots=True)
class InventoryReport:
    product_code: str
    product_kind: str
    domain_code: str
    initialization_time: datetime
    directory_urls: tuple[str, ...]
    inspected_forecast_hours: tuple[int, ...]
    remote_object_count: int
    remote_bytes_observed: int
    unknown_size_count: int
    enabled_object_count: int
    enabled_bytes_observed: int
    configured_ignored_count: int
    unknown_object_count: int
    parser_error_count: int
    missing_enabled_field_hours: tuple[tuple[str, int], ...]
    estimated_enabled_bytes_per_run: int | None
    estimated_enabled_raw_bytes_per_day: int | None
    estimated_processed_bytes_per_day: int | None
    objects: tuple[InventoryObject, ...]

    def to_dict(self, *, include_objects: bool = True) -> dict[str, Any]:
        reference_time = self.initialization_time.isoformat().replace("+00:00", "Z")
        result: dict[str, Any] = {
            "product": self.product_code,
            "product_kind": self.product_kind,
            "reference_time_semantics": (
                "initialization_time" if self.product_kind == "forecast" else "valid_time"
            ),
            "domain": self.domain_code,
            "reference_time": reference_time,
            "initialization_time": reference_time if self.product_kind == "forecast" else None,
            "analysis_valid_time": (
                reference_time if self.product_kind != "forecast" else None
            ),
            "directory_urls": list(self.directory_urls),
            "inspected_forecast_hours": (
                list(self.inspected_forecast_hours)
                if self.product_kind == "forecast"
                else []
            ),
            "inspected_time_offsets": list(self.inspected_forecast_hours),
            "remote_object_count": self.remote_object_count,
            "remote_bytes_observed": self.remote_bytes_observed,
            "unknown_size_count": self.unknown_size_count,
            "enabled_object_count": self.enabled_object_count,
            "enabled_bytes_observed": self.enabled_bytes_observed,
            "configured_ignored_count": self.configured_ignored_count,
            "unknown_object_count": self.unknown_object_count,
            "parser_error_count": self.parser_error_count,
            "missing_enabled_field_hours": [
                {
                    "field": field,
                    "forecast_hour": hour if self.product_kind == "forecast" else None,
                    "time_offset": hour,
                }
                for field, hour in self.missing_enabled_field_hours
            ],
            "estimated_enabled_bytes_per_run": self.estimated_enabled_bytes_per_run,
            "estimated_enabled_raw_bytes_per_day": self.estimated_enabled_raw_bytes_per_day,
            "estimated_processed_bytes_per_day": self.estimated_processed_bytes_per_day,
        }
        if include_objects:
            result["objects"] = [
                {
                    "filename": item.remote.filename,
                    "url": item.remote.url,
                    "size_bytes": item.remote.size_bytes,
                    "size_is_exact": item.remote.size_is_exact,
                    "disposition": item.disposition.value,
                    "field_code": item.field_code,
                    "parameter": item.parsed.parameter if item.parsed else None,
                    "source_level": item.parsed.source_level if item.parsed else None,
                    "forecast_hour": (
                        item.parsed.forecast_hour
                        if item.parsed and self.product_kind == "forecast"
                        else None
                    ),
                    "time_offset": item.parsed.forecast_hour if item.parsed else None,
                    "valid_time": (
                        item.parsed.valid_time.isoformat().replace("+00:00", "Z")
                        if item.parsed
                        else None
                    ),
                    "interval_start": (
                        item.parsed.interval_start.isoformat().replace("+00:00", "Z")
                        if item.parsed and item.parsed.interval_start
                        else None
                    ),
                    "interval_end": (
                        item.parsed.interval_end.isoformat().replace("+00:00", "Z")
                        if item.parsed and item.parsed.interval_end
                        else None
                    ),
                    "accumulation_hours": (
                        item.parsed.accumulation_hours if item.parsed else None
                    ),
                    "analysis_revision": (
                        item.parsed.analysis_revision if item.parsed else None
                    ),
                    "expected_source_unit": item.expected_source_unit,
                    "reason": item.reason,
                }
                for item in self.objects
            ]
        return result


def inspect_run(
    adapter: ProductSourceAdapter,
    run: RemoteRun,
    *,
    forecast_hours: tuple[int, ...] | None = None,
    use_today_alias: bool = False,
) -> InventoryReport:
    hours = tuple(sorted(set(forecast_hours or adapter.config.forecast_hours.values())))
    if not hours:
        raise ValueError("at least one forecast hour must be inspected")
    remote_objects = adapter.list_run_objects(
        run, forecast_hours=hours, use_today_alias=use_today_alias
    )
    inventory_objects: list[InventoryObject] = []
    observed_enabled: set[tuple[str, int]] = set()

    for remote in remote_objects:
        try:
            parsed = adapter.parse_object(remote, expected_run=run)
        except ValueError as exc:
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=None,
                    disposition=InventoryDisposition.PARSER_ERROR,
                    field_code=None,
                    expected_source_unit=None,
                    reason=str(exc),
                )
            )
            continue

        field = adapter.field_for(parsed)
        if field is None:
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=parsed,
                    disposition=InventoryDisposition.UNKNOWN,
                    field_code=None,
                    expected_source_unit=None,
                    reason="source field is not present in validated configuration",
                )
            )
        elif not field.availability.includes(parsed.forecast_hour):
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=parsed,
                    disposition=InventoryDisposition.IGNORED,
                    field_code=field.code,
                    expected_source_unit=field.source.expected_unit,
                    reason="source field is outside its configured forecast-hour availability",
                )
            )
        elif not field.download_enabled:
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=parsed,
                    disposition=InventoryDisposition.IGNORED,
                    field_code=field.code,
                    expected_source_unit=field.source.expected_unit,
                    reason="field is configured but download is disabled",
                )
            )
        elif parsed.data_format not in adapter.config.source_formats:
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=parsed,
                    disposition=InventoryDisposition.IGNORED,
                    field_code=field.code,
                    expected_source_unit=field.source.expected_unit,
                    reason="source format is not enabled for this product",
                )
            )
        else:
            observed_enabled.add((field.code, parsed.forecast_hour))
            inventory_objects.append(
                InventoryObject(
                    remote=remote,
                    parsed=parsed,
                    disposition=InventoryDisposition.ENABLED,
                    field_code=field.code,
                    expected_source_unit=field.source.expected_unit,
                    reason="field is enabled for download",
                )
            )

    expected_all = adapter.expected_manifest(run).expected_field_hours
    expected_inspected = {item for item in expected_all if item[1] in hours}
    missing = tuple(sorted(expected_inspected - observed_enabled))
    enabled = [
        item for item in inventory_objects if item.disposition is InventoryDisposition.ENABLED
    ]
    enabled_known_sizes = [item.remote.size_bytes for item in enabled if item.remote.size_bytes]
    enabled_bytes = sum(enabled_known_sizes)
    observed_expected_slots = len(expected_inspected)
    total_expected_slots = len(expected_all)
    estimated_run_bytes: int | None = None
    if enabled_known_sizes and observed_expected_slots:
        estimated_run_bytes = round(enabled_bytes * total_expected_slots / observed_expected_slots)
    runs_per_day = len(adapter.config.run_hours_utc)
    daily_raw = (
        estimated_run_bytes * runs_per_day
        if estimated_run_bytes is not None and adapter.config.kind == "forecast"
        else None
    )
    daily_processed = (
        round(daily_raw * adapter.config.estimates.processed_to_raw_ratio)
        if daily_raw is not None
        else None
    )

    return InventoryReport(
        product_code=run.product_code,
        product_kind=adapter.config.kind,
        domain_code=run.domain_code,
        initialization_time=run.initialization_time.astimezone(UTC),
        directory_urls=tuple(
            adapter.directory_url(run, hour, use_today_alias=use_today_alias) for hour in hours
        ),
        inspected_forecast_hours=hours,
        remote_object_count=len(inventory_objects),
        remote_bytes_observed=sum(item.remote.size_bytes or 0 for item in inventory_objects),
        unknown_size_count=sum(item.remote.size_bytes is None for item in inventory_objects),
        enabled_object_count=len(enabled),
        enabled_bytes_observed=enabled_bytes,
        configured_ignored_count=sum(
            item.disposition is InventoryDisposition.IGNORED for item in inventory_objects
        ),
        unknown_object_count=sum(
            item.disposition is InventoryDisposition.UNKNOWN for item in inventory_objects
        ),
        parser_error_count=sum(
            item.disposition is InventoryDisposition.PARSER_ERROR for item in inventory_objects
        ),
        missing_enabled_field_hours=missing,
        estimated_enabled_bytes_per_run=estimated_run_bytes,
        estimated_enabled_raw_bytes_per_day=daily_raw,
        estimated_processed_bytes_per_day=daily_processed,
        objects=tuple(inventory_objects),
    )
