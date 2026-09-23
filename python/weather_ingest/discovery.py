"""Automatic, idempotent discovery of processing-enabled ECCC objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from weather_ingest.adapters.base import ProductSourceAdapter
from weather_ingest.config import ProductConfig
from weather_ingest.models import ParsedSourceObject, RemoteRun


@dataclass(frozen=True, slots=True)
class DiscoveredObject:
    """A remote object selected for registration and processing."""

    run: RemoteRun
    parsed: ParsedSourceObject
    field_code: str


def _asset_is_current(
    data_root: Path,
    config: ProductConfig,
    field_code: str,
    slot: tuple[str, str] | None,
) -> bool:
    if slot is None:
        return False
    relative_path, conversion_key = slot
    field = config.field(field_code)
    if conversion_key != field.conversion_key:
        return False
    destination = (data_root / relative_path).resolve()
    try:
        destination.relative_to(data_root.resolve())
    except ValueError:
        return False
    if not destination.is_file():
        return False
    if config.domains[0].grid.startswith("RLatLon"):
        return Path(str(destination) + ".aux.xml").is_file()
    return True


def discover_available_objects(
    config: ProductConfig,
    adapter: ProductSourceAdapter,
    *,
    now: datetime,
    data_root: Path,
    available_slots: dict[tuple[datetime, str, int], tuple[str, str]],
    limit: int = 512,
) -> tuple[DiscoveredObject, ...]:
    """Inspect missing run/hour slots and return newly available source objects.

    Candidate runs are limited to the product retry window. Existing COGs with
    the current conversion key are excluded before any directory request, so a
    completed run causes no provider traffic on later hourly checks.
    """

    if now.tzinfo is None:
        raise ValueError("automatic discovery time must be timezone-aware")
    if limit < 1:
        raise ValueError("automatic discovery limit must be positive")

    selected: list[DiscoveredObject] = []
    seen_keys: set[str] = set()
    runs = adapter.list_candidate_runs(
        now.astimezone(UTC),
        lookback_hours=config.discovery.retry_window_hours,
    )
    for run in runs:
        expected = {
            (field_code, forecast_hour)
            for field_code, forecast_hour in adapter.expected_manifest(run).expected_field_hours
            if config.field(field_code).processing_enabled
        }
        missing = {
            (field_code, forecast_hour)
            for field_code, forecast_hour in expected
            if not _asset_is_current(
                data_root,
                config,
                field_code,
                available_slots.get(
                    (run.initialization_time.astimezone(UTC), field_code, forecast_hour)
                ),
            )
        }
        if not missing:
            continue
        for forecast_hour in sorted({hour for _field, hour in missing}):
            try:
                remote_objects = adapter.list_run_objects(
                    run,
                    forecast_hours=(forecast_hour,),
                    use_today_alias=False,
                )
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    continue
                raise
            for remote in remote_objects:
                try:
                    parsed = adapter.parse_object(remote, expected_run=run)
                except ValueError:
                    continue
                field = adapter.field_for(parsed)
                if (
                    field is None
                    or (field.code, parsed.forecast_hour) not in missing
                    or not field.download_enabled
                    or not field.processing_enabled
                    or parsed.data_format not in config.source_formats
                ):
                    continue
                canonical_key = adapter.canonical_object_key(remote)
                if canonical_key in seen_keys:
                    continue
                seen_keys.add(canonical_key)
                selected.append(DiscoveredObject(run, parsed, field.code))
                if len(selected) == limit:
                    return tuple(selected)
    return tuple(selected)
