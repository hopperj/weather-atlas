"""Read-only admission checks for bounded smoke scenarios."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from weather_ingest.fbp_fuels import has_supported_cffeps_fuel
from weather_ingest.fire_scenarios import FireWeatherMode, SmokeScenarioConfig
from weather_ingest.flexpart_releases import (
    MAXIMUM_RELEASE_GROUPS_PER_EVENT_HOUR,
    MINIMUM_PARTICLES_PER_RELEASE,
)
from weather_ingest.gfs_profiles import resolve_complete_cycle


class SmokePreflightError(ValueError):
    """A scenario cannot be run safely with the locally available inputs."""


@dataclass(frozen=True, slots=True)
class SmokeAdmissionLimits:
    maximum_horizon_hours: int
    maximum_domain_cells: int
    maximum_particles: int
    maximum_releases: int
    minimum_free_bytes: int
    maximum_storage_bytes: int = 512 * 1024**3


@dataclass(frozen=True, slots=True)
class SmokePreflightResult:
    gfs_cycle: datetime
    fire_event_count: int
    domain_cells: int
    estimated_releases: int
    particle_count: int
    estimated_output_bytes: int
    available_bytes: int

    def public_estimate(self) -> dict[str, int]:
        return {
            "fireEventCount": self.fire_event_count,
            "domainCells": self.domain_cells,
            "estimatedReleases": self.estimated_releases,
            "particleCount": self.particle_count,
            "estimatedOutputBytes": self.estimated_output_bytes,
        }


@lru_cache(maxsize=16)
def _verified_manifest(
    path_text: str, modified_ns: int, size_bytes: int
) -> tuple[dict[str, Any], tuple[Path, ...]]:
    del modified_ns, size_bytes
    payload, files = resolve_complete_cycle(Path(path_text))
    return payload, tuple(files)


def _select_complete_cycle(data_root: Path, scenario: SmokeScenarioConfig) -> dict[str, Any]:
    candidates = sorted(
        data_root.glob("raw/noaa/gfs/global_1p00/*/*/*/*/manifest.json"), reverse=True
    )
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            stat = candidate.stat()
            payload, _files = _verified_manifest(
                str(candidate.resolve()), stat.st_mtime_ns, stat.st_size
            )
            valid_times = [
                datetime.fromisoformat(item["valid_time"].replace("Z", "+00:00"))
                for item in payload["files"]
            ]
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if min(valid_times) <= scenario.start_time and scenario.end_time <= max(valid_times):
            return payload
    raise SmokePreflightError(
        "No checksum-verified complete local GFS cycle covers the requested start and end time"
    )


def _selected_events(data_root: Path, scenario: SmokeScenarioConfig) -> int:
    path = data_root / "derived/smoke/fire-events/latest.json"
    if not path.is_file() or path.is_symlink():
        raise SmokePreflightError("No reconciled fire-event snapshot is available")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload["events"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SmokePreflightError("The reconciled fire-event snapshot is invalid") from exc
    if not isinstance(events, list):
        raise SmokePreflightError("The reconciled fire-event snapshot is invalid")

    source_window_start = scenario.start_time - timedelta(hours=24)

    def overlaps_source_window(event: dict[str, Any]) -> bool:
        try:
            first = datetime.fromisoformat(
                str(event["first_observed_at"]).replace("Z", "+00:00")
            )
            last = datetime.fromisoformat(
                str(event["last_observed_at"]).replace("Z", "+00:00")
            )
        except (KeyError, TypeError, ValueError):
            return False
        return (
            first < scenario.end_time
            and source_window_start <= last < scenario.end_time
        )

    requested = set(scenario.event_ids)
    if requested:
        selected = {
            str(event.get("event_id")): event
            for event in events
            if isinstance(event, dict) and event.get("event_id") in requested
        }
        missing = sorted(requested - selected.keys())
        if missing:
            raise SmokePreflightError(
                f"Selected fire event is absent from the current frozen snapshot: {missing[0]}"
            )
        west, south, east, north = scenario.bbox
        outside = sorted(
            event_id
            for event_id, event in selected.items()
            if not (
                isinstance(event.get("longitude"), int | float)
                and isinstance(event.get("latitude"), int | float)
                and west <= event["longitude"] <= east
                and south <= event["latitude"] <= north
            )
        )
        if outside:
            raise SmokePreflightError(
                f"Selected fire event falls outside the output domain: {outside[0]}"
            )
        outside_window = sorted(
            event_id
            for event_id, event in selected.items()
            if not overlaps_source_window(event)
        )
        if outside_window:
            raise SmokePreflightError(
                "Selected fire event is outside the simulation source window: "
                f"{outside_window[0]}"
            )
        unsupported_fuel = sorted(
            event_id
            for event_id, event in selected.items()
            if not has_supported_cffeps_fuel(event.get("fuel_types"))
        )
        if unsupported_fuel:
            raise SmokePreflightError(
                "Selected fire event has no CFFEPS-supported fuel: "
                f"{unsupported_fuel[0]}"
            )
        chosen = list(selected.values())
        if scenario.fire_weather_mode == FireWeatherMode.AUTOMATIC_CWFIS:
            missing_weather = sorted(
                event_id for event_id, event in selected.items() if not event.get("fire_weather")
            )
            if missing_weather:
                raise SmokePreflightError(
                    "Selected fire event has no archived CWFIS FFMC/DMC/DC state: "
                    f"{missing_weather[0]}"
                )
        return len(chosen)

    west, south, east, north = scenario.bbox
    chosen = [
        event
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("longitude"), int | float)
        and isinstance(event.get("latitude"), int | float)
        and west <= event["longitude"] <= east
        and south <= event["latitude"] <= north
        and overlaps_source_window(event)
        and has_supported_cffeps_fuel(event.get("fuel_types"))
    ]
    if scenario.fire_weather_mode == FireWeatherMode.AUTOMATIC_CWFIS:
        chosen = [event for event in chosen if event.get("fire_weather")]
    count = len(chosen)
    if count == 0:
        raise SmokePreflightError("The scenario domain contains no fire events")
    if count > 200:
        raise SmokePreflightError(
            "The scenario domain contains more than 200 fire events; select explicit events "
            "or reduce the bounding box"
        )
    return count


def preflight_smoke_scenario(
    data_root: Path,
    scenario: SmokeScenarioConfig,
    limits: SmokeAdmissionLimits,
) -> SmokePreflightResult:
    """Verify immutable inputs and estimate resources before a database write."""

    horizon_hours = (scenario.end_time - scenario.start_time).total_seconds() / 3600
    if horizon_hours > limits.maximum_horizon_hours:
        raise SmokePreflightError(
            f"Scenario horizon exceeds the configured {limits.maximum_horizon_hours}-hour limit"
        )
    if scenario.fire_weather_mode == FireWeatherMode.MANUAL and scenario.fire_weather is None:
        raise SmokePreflightError("Manual fire-weather mode requires FFMC, DMC, and DC")
    if scenario.particle_budget > limits.maximum_particles:
        raise SmokePreflightError(
            f"Particle budget exceeds the configured {limits.maximum_particles} limit"
        )

    west, south, east, north = scenario.bbox
    columns = math.ceil((east - west) / scenario.grid_spacing_degrees) + 1
    rows = math.ceil((north - south) / scenario.grid_spacing_degrees) + 1
    domain_cells = columns * rows
    if domain_cells > limits.maximum_domain_cells:
        raise SmokePreflightError(
            f"Output grid requires {domain_cells} cells; the configured limit is "
            f"{limits.maximum_domain_cells}"
        )

    gfs = _select_complete_cycle(data_root, scenario)
    event_count = _selected_events(data_root, scenario)
    release_hours = max(1, math.ceil(horizon_hours))
    estimated_releases = (
        event_count * release_hours * MAXIMUM_RELEASE_GROUPS_PER_EVENT_HOUR
    )
    if estimated_releases > limits.maximum_releases:
        raise SmokePreflightError(
            f"Estimated releases per species ({estimated_releases}) exceed the configured "
            f"limit ({limits.maximum_releases})"
        )
    minimum_particle_count = (
        estimated_releases
        * MINIMUM_PARTICLES_PER_RELEASE
        * len(scenario.species)
    )
    if scenario.particle_budget < minimum_particle_count:
        raise SmokePreflightError(
            f"Particle budget must be at least {minimum_particle_count} for the "
            "selected fires, duration, and species"
        )

    # Seven display fields plus compressed scientific/output overhead. This is deliberately
    # conservative and is an admission estimate, not a storage-accounting measurement.
    frame_count = release_hours + 1
    estimated_output_bytes = max(
        64 * 1024**2,
        domain_cells * frame_count * 7 * 4 * 4,
    )
    smoke_storage_bytes = sum(
        path.stat().st_size
        for namespace in (
            data_root / "derived/smoke/runs",
            data_root / "processed/local/flexpart_smoke",
        )
        if namespace.exists()
        for path in namespace.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    if smoke_storage_bytes + estimated_output_bytes > limits.maximum_storage_bytes:
        raise SmokePreflightError(
            "Smoke storage quota would be exceeded by the estimated run output"
        )
    try:
        available_bytes = shutil.disk_usage(data_root).free
    except OSError as exc:
        raise SmokePreflightError("Unable to inspect smoke-workspace disk capacity") from exc
    required_bytes = limits.minimum_free_bytes + estimated_output_bytes
    if available_bytes < required_bytes:
        raise SmokePreflightError(
            "Insufficient free storage for the configured reserve and estimated smoke output"
        )

    return SmokePreflightResult(
        gfs_cycle=datetime.fromisoformat(
            gfs["initialization_time"].replace("Z", "+00:00")
        ).astimezone(UTC),
        fire_event_count=event_count,
        domain_cells=domain_cells,
        estimated_releases=estimated_releases,
        particle_count=scenario.particle_budget,
        estimated_output_bytes=estimated_output_bytes,
        available_bytes=available_bytes,
    )
