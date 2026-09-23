"""Database-backed, bounded end-to-end CFFEPS and FLEXPART smoke jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import rasterio
import yaml
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from weather_common.db import SqlFileLoader

from weather_ingest.cffeps import (
    FUEL_INDEX,
    CffepsFire,
    EmissionRow,
    apply_cumulative_area_curve,
    run_cffeps,
    write_emission_bundle,
)
from weather_ingest.fbp_fuels import resolve_fbp_fuel
from weather_ingest.fire_scenarios import FireWeatherCodes, FireWeatherMode, SmokeScenarioConfig
from weather_ingest.flexpart_config import FlexpartDomain
from weather_ingest.flexpart_runner import (
    FlexpartRunLimits,
    derive_member_random_seed,
    prepare_species_runs,
    run_flexpart,
)
from weather_ingest.gfs_profiles import extract_cycle_profiles
from weather_ingest.smoke_outputs import derive_injection_height_cogs, derive_smoke_cogs

logger = logging.getLogger("weather_ingest.smoke")


def emission_registry_warnings(
    run_kind: str, factor_registry: dict[str, Any]
) -> list[str]:
    """Apply scientific-use policy without misrepresenting review status."""

    if run_kind == "validation":
        return []
    review_status = factor_registry.get("review", {}).get("status")
    if review_status == "approved":
        return []
    if (
        run_kind == "interactive"
        and factor_registry.get("scientific_status") == "validation_only"
    ):
        return [
            "Research-only run: emission factors are pending independent "
            "scientific review"
        ]
    raise ValueError(
        "operational smoke runs require an independently approved emissions registry"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_size(path: Path) -> int:
    """Count each inode once so run-local hard links do not inflate storage metrics."""

    seen: set[tuple[int, int]] = set()
    total = 0
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        stat = candidate.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity not in seen:
            seen.add(identity)
            total += stat.st_size
    return total


def claim_next_run(
    database_url: str,
    loader: SqlFileLoader | None = None,
    *,
    allowed_run_kind: str | None = None,
) -> str | None:
    sql = loader or SqlFileLoader()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            sql.load("simulation/claim_next_run.sql"),
            {"allowed_run_kind": allowed_run_kind},
        ).fetchone()
        return str(row["id"]) if row else None


def _raise_if_cancellation_requested(
    database_url: str, loader: SqlFileLoader, run_id: UUID
) -> None:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            loader.load("simulation/get_run_for_worker.sql"), {"run_id": run_id}
        ).fetchone()
    if row and row["status"] == "cancellation_requested":
        raise RuntimeError("simulation cancellation was requested")


def _transition(
    connection: Any,
    loader: SqlFileLoader,
    run_id: UUID,
    expected: str,
    new: str,
    *,
    metrics: dict[str, Any] | None = None,
    warnings: list[Any] | None = None,
    error: Exception | None = None,
) -> None:
    row = connection.execute(
        loader.load("simulation/transition_run.sql"),
        {
            "run_id": run_id,
            "expected_status": expected,
            "new_status": new,
            "metrics": Jsonb(metrics or {}),
            "warnings": Jsonb(warnings or []),
            "error_class": type(error).__name__ if error else None,
            "error_message": str(error)[:2000] if error else None,
        },
    ).fetchone()
    if row is None:
        raise RuntimeError(f"run {run_id} was not in expected state {expected}")


def _select_gfs_manifest(data_root: Path, start: datetime, end: datetime) -> Path:
    manifests = sorted(
        data_root.glob("raw/noaa/gfs/global_1p00/*/*/*/*/manifest.json"), reverse=True
    )
    for path in manifests:
        payload = json.loads(path.read_text(encoding="utf-8"))
        initialization = datetime.fromisoformat(
            payload["initialization_time"].replace("Z", "+00:00")
        )
        last = max(
            datetime.fromisoformat(item["valid_time"].replace("Z", "+00:00"))
            for item in payload["files"]
        )
        if initialization <= start and end <= last:
            return path
    raise FileNotFoundError("no complete GFS cycle covers the requested scenario")


def _load_events(
    data_root: Path, scenario: SmokeScenarioConfig, crosswalk_path: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    path = data_root / "derived/smoke/fire-events/latest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    if crosswalk_payload.get("schema_version") != 1:
        raise ValueError("unsupported fuel crosswalk")
    crosswalk = {
        str(source).upper(): str(target).upper()
        for source, target in crosswalk_payload["rules"].items()
    }
    selected = []
    warnings: list[str] = []
    matched_ids: set[str] = set()
    outside_ids: set[str] = set()
    requested = set(scenario.event_ids)
    west, south, east, north = scenario.bbox
    source_window_start = scenario.start_time - timedelta(hours=24)
    for event in payload["events"]:
        if requested and event["event_id"] not in requested:
            continue
        if requested and not (
            west <= event["longitude"] <= east and south <= event["latitude"] <= north
        ):
            matched_ids.add(event["event_id"])
            outside_ids.add(event["event_id"])
            continue
        if not requested and not (
            west <= event["longitude"] <= east and south <= event["latitude"] <= north
        ):
            continue
        matched_ids.add(event["event_id"])
        try:
            first_observed = datetime.fromisoformat(
                event["first_observed_at"].replace("Z", "+00:00")
            )
            last_observed = datetime.fromisoformat(
                event["last_observed_at"].replace("Z", "+00:00")
            )
        except (KeyError, TypeError, ValueError):
            warnings.append(f"excluded_invalid_event_time:{event['event_id']}")
            continue
        if not (
            first_observed < scenario.end_time
            and source_window_start <= last_observed < scenario.end_time
        ):
            warnings.append(f"excluded_outside_source_window:{event['event_id']}")
            continue
        mapped_fuel = None
        for raw_fuel in event["fuel_types"]:
            candidate = resolve_fbp_fuel(str(raw_fuel), crosswalk)
            if candidate is not None and candidate.model_code.split("_")[0] in FUEL_INDEX:
                mapped_fuel = candidate
                break
        if mapped_fuel is None:
            warnings.append(f"excluded_nonburnable_or_unmapped_fuel:{event['event_id']}")
            continue
        if (
            scenario.fire_weather_mode == FireWeatherMode.AUTOMATIC_CWFIS
            and not event.get("fire_weather")
        ):
            warnings.append(f"excluded_missing_cwfis_fire_weather:{event['event_id']}")
            continue
        selected.append(
            event
            | {
                "model_fuel_type": mapped_fuel.model_code,
                "source_fuel_type": mapped_fuel.source_code,
                "percent_conifer": mapped_fuel.percent_conifer,
                "percent_dead_fir": mapped_fuel.percent_dead_fir,
                "grass_curing_percent": mapped_fuel.grass_curing_percent,
                "fuel_parameter_source": mapped_fuel.parameter_source,
            }
        )
    if requested - matched_ids:
        raise ValueError("one or more selected fire events are absent from the frozen snapshot")
    if outside_ids:
        raise ValueError("one or more selected fire events falls outside the output domain")
    if requested and any(warning.rsplit(":", 1)[-1] in requested for warning in warnings):
        raise ValueError(
            "one or more selected fire events is outside the causal source window, "
            "lacks a supported fuel, or lacks archived CWFIS state"
        )
    if not selected:
        raise ValueError("scenario selected no fire events")
    if len(selected) > 200:
        raise ValueError(
            "scenario selected more than 200 fire events; select explicit events or "
            "reduce the bounding box"
        )
    return selected, warnings


def _model_builds(
    connection: Any,
    loader: SqlFileLoader,
    config_path: Path,
    executables: dict[str, Path],
) -> dict[str, int]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported model-build registry")
    build_ids: dict[str, int] = {}
    for name, executable in executables.items():
        definition = payload["models"][name]
        row = connection.execute(
            loader.load("simulation/register_model_build.sql"),
            {
                "model_name": name,
                "model_version": definition["version"],
                "source_sha256": definition["source_sha256"],
                "patch_set_sha256": definition["patch_set_sha256"],
                "executable_sha256": _sha256(executable),
                "container_digest": os.getenv("SMOKE_CONTAINER_DIGEST"),
                "toolchain": Jsonb(definition["toolchain"]),
            },
        ).fetchone()
        if row is None:
            raise RuntimeError(f"unable to register {name} model build")
        build_ids[name] = int(row["id"])
    return build_ids


def _publish_catalogue(
    connection: Any,
    loader: SqlFileLoader,
    run_id: UUID,
    catalogue_run_time: datetime,
    forecast_reference_time: datetime,
    assets: list[dict[str, Any]],
    data_root: Path,
    source_manifest: dict[str, Any],
    required_fields: list[str],
    output_manifest: Path,
) -> int:
    product_run = connection.execute(
        loader.load("ingestion/upsert_product_run.sql"),
        {
            "product_code": "flexpart_smoke",
            "domain_code": "scenario_domain",
            "run_time": catalogue_run_time,
            "source_status": "complete",
            "processing_status": "processing",
            "source_manifest": Jsonb(source_manifest),
            "expected_asset_count": len(assets),
            "discovered_asset_count": len(assets),
        },
    ).fetchone()
    if product_run is None:
        raise RuntimeError("unable to create smoke catalogue run")
    for asset in assets:
        valid_time = datetime.fromisoformat(asset["valid_time"].replace("Z", "+00:00"))
        product_time = connection.execute(
            loader.load("ingestion/upsert_product_time.sql"),
            {
                "product_run_id": product_run["id"],
                "valid_time": valid_time,
                "forecast_hour": int(
                    (valid_time - forecast_reference_time).total_seconds() // 3600
                ),
                "interval_start": None,
                "interval_end": None,
                "time_kind": "instant",
            },
        ).fetchone()
        field = connection.execute(
            loader.load("ingestion/resolve_product_field.sql"),
            {"product_code": "flexpart_smoke", "field_code": asset["field"]},
        ).fetchone()
        if product_time is None or field is None:
            raise RuntimeError(f"catalogue mapping is missing for {asset['field']}")
        absolute = data_root / asset["relative_path"]
        with rasterio.open(absolute) as source:
            bounds = source.bounds
            values = source.read(1, masked=True)
            minimum = float(values.min()) if values.count() else None
            maximum = float(values.max()) if values.count() else None
            width, height = source.width, source.height
        bounds_wkt = (
            f"POLYGON(({bounds.left} {bounds.bottom}, {bounds.right} {bounds.bottom}, "
            f"{bounds.right} {bounds.top}, {bounds.left} {bounds.top}, "
            f"{bounds.left} {bounds.bottom}))"
        )
        connection.execute(
            loader.load("ingestion/upsert_asset.sql"),
            {
                "product_id": field["product_id"],
                "product_run_id": product_run["id"],
                "product_time_id": product_time["id"],
                "product_field_id": field["product_field_id"],
                "vertical_level_id": field["vertical_level_id"],
                "asset_role": "derived_cog",
                "relative_path": asset["relative_path"],
                "mime_type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "file_size_bytes": asset["size_bytes"],
                "sha256": asset["sha256"],
                "projection": "EPSG:4326",
                "bounds_wkt": bounds_wkt,
                "width": width,
                "height": height,
                "band_count": 1,
                "nodata_value": -9999.0,
                "minimum_value": minimum,
                "maximum_value": maximum,
                "statistics": Jsonb({"minimum": minimum, "maximum": maximum}),
                "provenance": Jsonb({"simulation_run_id": str(run_id), "unit": asset["unit"]}),
                "status": "available",
            },
        ).fetchone()
    connection.execute(
        loader.load("ingestion/finalize_product_run.sql"),
        {"product_run_id": product_run["id"], "required_field_codes": required_fields},
    ).fetchone()
    relative_manifest = output_manifest.relative_to(data_root).as_posix()
    connection.execute(
        loader.load("simulation/link_product_run.sql"),
        {
            "run_id": run_id,
            "product_run_id": product_run["id"],
            "output_manifest_path": relative_manifest,
        },
    ).fetchone()
    return int(product_run["id"])


def execute_claimed_run(
    run_id: str,
    *,
    data_root: Path,
    config_root: Path,
    cffeps_executable: Path,
    flexpart_root: Path,
    flexpart_executable: Path,
    database_url: str,
) -> dict[str, Any]:
    loader = SqlFileLoader()
    run_uuid = UUID(run_id)
    work = data_root / "temporary/smoke" / run_id[:12]
    archive = data_root / "derived/smoke/runs" / run_id
    processed = data_root / "processed/local/flexpart_smoke" / run_id
    current_state = "resolving_inputs"
    run_warnings: list[str] = []
    run_started = time.perf_counter()
    phase_started = run_started
    logger.info(
        "smoke_run_started",
        extra={"simulation_run_id": run_id, "task_phase": current_state},
    )
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                loader.load("simulation/get_run_for_worker.sql"), {"run_id": run_uuid}
            ).fetchone()
            if row is None or row["status"] != current_state:
                raise RuntimeError("simulation run is not claimed")
            scenario = SmokeScenarioConfig.model_validate(row["canonical_config"])
            factor_registry = yaml.safe_load(
                (config_root / "smoke/emission_factors.yaml").read_text(
                    encoding="utf-8"
                )
            )
            run_warnings.extend(
                emission_registry_warnings(row["run_kind"], factor_registry)
            )
            maximum_horizon = int(os.getenv("SMOKE_MAX_HORIZON_HOURS", "24"))
            horizon_hours = (
                scenario.end_time - scenario.start_time
            ).total_seconds() / 3600
            if horizon_hours > maximum_horizon:
                raise ValueError("scenario exceeds the configured smoke horizon")
            maximum_particles = int(os.getenv("SMOKE_MAXIMUM_PARTICLES", "1000000"))
            if scenario.particle_budget > maximum_particles:
                raise ValueError("scenario exceeds the configured particle limit")
            west, south, east, north = scenario.bbox
            domain_cells = (
                math.ceil((east - west) / scenario.grid_spacing_degrees) + 1
            ) * (math.ceil((north - south) / scenario.grid_spacing_degrees) + 1)
            if domain_cells > int(os.getenv("SMOKE_MAX_DOMAIN_CELLS", "50000")):
                raise ValueError("scenario exceeds the configured output-grid limit")
            minimum_free_bytes = int(
                os.getenv("SMOKE_MINIMUM_FREE_BYTES", "21474836480")
            )
            if shutil.disk_usage(data_root).free < minimum_free_bytes:
                raise RuntimeError("smoke workspace is below its free-space admission reserve")
            maximum_storage_bytes = int(
                os.getenv("SMOKE_MAXIMUM_STORAGE_BYTES", "549755813888")
            )
            stored_smoke_bytes = sum(
                _tree_size(namespace)
                for namespace in (
                    data_root / "derived/smoke/runs",
                    data_root / "processed/local/flexpart_smoke",
                )
                if namespace.exists()
            )
            if stored_smoke_bytes >= maximum_storage_bytes:
                raise RuntimeError("smoke storage quota has been reached")
            if (
                scenario.fire_weather_mode == FireWeatherMode.MANUAL
                and scenario.fire_weather is None
            ):
                raise ValueError(
                    "manual fire-weather mode requires explicit FFMC/DMC/DC"
                )
            requested_at = row["requested_at"]
            gfs_manifest = _select_gfs_manifest(data_root, scenario.start_time, scenario.end_time)
            gfs_payload = json.loads(gfs_manifest.read_text(encoding="utf-8"))
            events, event_warnings = _load_events(
                data_root, scenario, config_root / "smoke/fuel_crosswalk.yaml"
            )
            run_warnings.extend(event_warnings)
            newest_fire_observation = max(
                datetime.fromisoformat(event["last_observed_at"].replace("Z", "+00:00"))
                for event in events
            )
            build_ids = _model_builds(
                connection,
                loader,
                config_root / "smoke/model_builds.yaml",
                {"CFFEPS": cffeps_executable, "FLEXPART": flexpart_executable},
            )
            work.mkdir(parents=True, exist_ok=False)
            (work / "input").mkdir()
            copied_gfs_manifest = work / "input/gfs_manifest.json"
            shutil.copy2(gfs_manifest, copied_gfs_manifest)
            event_snapshot = data_root / "derived/smoke/fire-events/latest.json"
            copied_event_snapshot = work / "input/fire_snapshot.json"
            shutil.copy2(event_snapshot, copied_event_snapshot)
            input_manifest = work / "input/manifest.json"
            input_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "scenario_config_sha256": scenario.config_sha256,
                        "gfs_cycle_time": gfs_payload["initialization_time"],
                        "gfs_manifest_sha256": _sha256(copied_gfs_manifest),
                        "fire_snapshot_sha256": _sha256(copied_event_snapshot),
                        "selected_event_ids": [event["event_id"] for event in events],
                        "warnings": run_warnings,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            input_manifest_relative = (
                (archive / "input/manifest.json").relative_to(data_root).as_posix()
            )
            connection.execute(
                loader.load("simulation/record_resolved_inputs.sql"),
                {
                    "run_id": run_uuid,
                    "gfs_cycle_time": datetime.fromisoformat(
                        gfs_payload["initialization_time"].replace("Z", "+00:00")
                    ),
                    "cffeps_build_id": build_ids["CFFEPS"],
                    "flexpart_build_id": build_ids["FLEXPART"],
                    "input_manifest_path": input_manifest_relative,
                },
            ).fetchone()
            _transition(
                connection,
                loader,
                run_uuid,
                current_state,
                "emissions_running",
                metrics={
                    "resolving_inputs_seconds": time.perf_counter() - phase_started,
                    "gfs_input_age_seconds": max(
                        0.0,
                        (
                            requested_at
                            - datetime.fromisoformat(
                                gfs_payload["initialization_time"].replace("Z", "+00:00")
                            )
                        ).total_seconds(),
                    ),
                    "fire_input_age_seconds": max(
                        0.0, (requested_at - newest_fire_observation).total_seconds()
                    ),
                },
                warnings=run_warnings,
            )
            current_state = "emissions_running"
            phase_started = time.perf_counter()
            logger.info(
                "smoke_run_phase",
                extra={"simulation_run_id": run_id, "task_phase": current_state},
            )

        all_rows: list[EmissionRow] = []
        cffeps_manifests: list[dict[str, Any]] = []
        profile_cache: dict[tuple[int, int], tuple[list[Any], dict[str, Any]]] = {}
        for index, event in enumerate(events):
            if index % 10 == 0:
                _raise_if_cancellation_requested(database_url, loader, run_uuid)
            cache_key = (round(event["latitude"]), round(event["longitude"]))
            if cache_key not in profile_cache:
                profile_cache[cache_key] = extract_cycle_profiles(
                    gfs_manifest, event["latitude"], event["longitude"]
                )
            cached_profiles, profile_provenance = profile_cache[cache_key]
            profiles = [
                replace(profile, latitude=event["latitude"], longitude=event["longitude"])
                for profile in cached_profiles
                if scenario.start_time <= profile.valid_time < scenario.end_time
            ]
            detected = datetime.fromisoformat(event["last_observed_at"].replace("Z", "+00:00"))
            if scenario.fire_weather_mode == FireWeatherMode.MANUAL:
                fire_weather = scenario.fire_weather
                fire_weather_provenance = {
                    "source": "manual_scenario_override",
                    "scenario_config_sha256": scenario.config_sha256,
                }
            else:
                raw_fire_weather = event.get("fire_weather")
                if not isinstance(raw_fire_weather, dict):
                    raise ValueError(
                        f"fire event {event['event_id']} has no frozen CWFIS state"
                    )
                fire_weather = FireWeatherCodes.model_validate(
                    {key: raw_fire_weather[key] for key in ("ffmc", "dmc", "dc")}
                )
                fire_weather_provenance = {
                    key: value
                    for key, value in raw_fire_weather.items()
                    if key not in {"ffmc", "dmc", "dc"}
                }
            assert fire_weather is not None
            fire = CffepsFire(
                event_id=event["event_id"],
                latitude=event["latitude"],
                longitude=event["longitude"],
                fuel_type=event["model_fuel_type"],
                estimated_area_ha=max(event["maximum_estimated_area_ha"], 0.01),
                detected_at=detected,
                ffmc=fire_weather.ffmc,
                dmc=fire_weather.dmc,
                dc=fire_weather.dc,
                percent_conifer=event["percent_conifer"],
                percent_dead_fir=event["percent_dead_fir"],
                grass_curing_percent=event["grass_curing_percent"],
            )
            rows, manifest = run_cffeps(
                run_id=run_id,
                fire=fire,
                profiles=profiles,
                executable=cffeps_executable,
                work_dir=work / f"cffeps-{index:04d}",
                emission_factors_path=config_root / "smoke/emission_factors.yaml",
                species=scenario.species,
                uncertainty=scenario.uncertainty.value,
            )
            if scenario.area_mode.value == "user_area_curve":
                rows, area_manifest = apply_cumulative_area_curve(
                    rows,
                    tuple((point.time, point.area_ha) for point in scenario.area_curve),
                )
                manifest.update(area_manifest)
                manifest["mass_kg_by_species"] = {
                    species: sum(
                        row.emitted_mass_kg for row in rows if row.species == species
                    )
                    for species in scenario.species
                }
            else:
                manifest["area_mode"] = scenario.area_mode.value
            manifest["meteorology"] = profile_provenance
            manifest["fire_weather"] = {
                "ffmc": fire_weather.ffmc,
                "dmc": fire_weather.dmc,
                "dc": fire_weather.dc,
                **fire_weather_provenance,
            }
            manifest["fuel_crosswalk"] = {
                "source_code": event["source_fuel_type"],
                "model_code": event["model_fuel_type"],
                "parameter_source": event["fuel_parameter_source"],
            }
            all_rows.extend(rows)
            cffeps_manifests.append(manifest)
        mass_by_species = {
            species: sum(row.emitted_mass_kg for row in all_rows if row.species == species)
            for species in scenario.species
        }
        emission_manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "run_kind": row["run_kind"],
            "event_count": len(events),
            "cffeps_runs": cffeps_manifests,
            "mass_kg_by_species": mass_by_species,
        }
        emission_path = work / "input/emissions.nc"
        write_emission_bundle(emission_path, all_rows, emission_manifest)

        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            _transition(
                connection,
                loader,
                run_uuid,
                current_state,
                "transport_running",
                metrics={
                    "event_count": len(events),
                    "emission_row_count": len(all_rows),
                    "emissions_seconds": time.perf_counter() - phase_started,
                },
            )
            current_state = "transport_running"
            phase_started = time.perf_counter()
            logger.info(
                "smoke_run_phase",
                extra={"simulation_run_id": run_id, "task_phase": current_state},
            )
        limits = FlexpartRunLimits(
            timeout_seconds=int(os.getenv("SMOKE_RUN_TIMEOUT_SECONDS", "10800")),
            maximum_output_bytes=int(
                os.getenv("SMOKE_MAXIMUM_OUTPUT_BYTES", "21474836480")
            ),
            maximum_releases=int(os.getenv("SMOKE_MAXIMUM_RELEASES", "20000")),
            threads=int(os.getenv("SMOKE_FLEXPART_THREADS", "8")),
        )
        domain = FlexpartDomain(*scenario.bbox, spacing=scenario.grid_spacing_degrees)
        member_manifests = prepare_species_runs(
            parent_dir=work / "transport",
            flexpart_root=flexpart_root,
            gfs_manifest=gfs_manifest,
            rows=all_rows,
            species=scenario.species,
            start=scenario.start_time,
            end=scenario.end_time,
            domain=domain,
            particle_budget_per_species=max(
                10_000, scenario.particle_budget // len(scenario.species)
            ),
            limits=limits,
        )
        transport_results = {}
        for species in scenario.species:
            _raise_if_cancellation_requested(database_url, loader, run_uuid)
            transport_results[species] = run_flexpart(
                work / "transport" / species.lower(),
                flexpart_executable,
                limits,
                random_seed=derive_member_random_seed(scenario.random_seed, species),
            )

        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            _transition(
                connection,
                loader,
                run_uuid,
                current_state,
                "processing_outputs",
                metrics={"transport_seconds": time.perf_counter() - phase_started},
            )
            current_state = "processing_outputs"
            phase_started = time.perf_counter()
            logger.info(
                "smoke_run_phase",
                extra={"simulation_run_id": run_id, "task_phase": current_state},
            )
        assets: list[dict[str, Any]] = []
        member_output_manifests: dict[str, dict[str, Any]] = {}
        reference_netcdf: Path | None = None
        for species in scenario.species:
            netcdf = next((work / "transport" / species.lower() / "output").glob("grid_conc_*.nc"))
            reference_netcdf = reference_netcdf or netcdf
            product_manifest = derive_smoke_cogs(
                netcdf,
                processed,
                expected_hours=max(1, math.ceil(horizon_hours)),
            )
            member_output_manifests[species] = product_manifest
            for asset in product_manifest["assets"]:
                absolute = Path(asset["relative_path"])
                asset["relative_path"] = absolute.relative_to(data_root).as_posix()
                assets.append(asset)
        if reference_netcdf is None:
            raise RuntimeError("no FLEXPART member output was produced")
        injection_manifest = derive_injection_height_cogs(all_rows, reference_netcdf, processed)
        for asset in injection_manifest["assets"]:
            absolute = Path(asset["relative_path"])
            asset["relative_path"] = absolute.relative_to(data_root).as_posix()
            assets.append(asset)
        processed_manifest = processed / "manifest.json"
        processed_manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "member_outputs": member_output_manifests,
                    "injection_height": injection_manifest,
                    "asset_count": len(assets),
                    "assets": assets,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_peak_bytes = _tree_size(work) + _tree_size(processed)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(work, archive)
        output_manifest = archive / "manifest.json"
        final_manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "run_kind": row["run_kind"],
            "scenario_config_sha256": scenario.config_sha256,
            "gfs_manifest_sha256": _sha256(gfs_manifest),
            "event_snapshot_sha256": _sha256(event_snapshot),
            "cffeps_executable_sha256": _sha256(cffeps_executable),
            "flexpart_executable_sha256": _sha256(flexpart_executable),
            "member_manifests": member_manifests,
            "transport_results": transport_results,
            "mass_kg_by_species": mass_by_species,
            "assets": assets,
            "primary_emissions_only": True,
        }
        output_manifest.write_text(
            json.dumps(final_manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            _transition(
                connection,
                loader,
                run_uuid,
                current_state,
                "publishing",
                metrics={"processing_outputs_seconds": time.perf_counter() - phase_started},
            )
            current_state = "publishing"
            phase_started = time.perf_counter()
            logger.info(
                "smoke_run_phase",
                extra={"simulation_run_id": run_id, "task_phase": current_state},
            )
            for input_kind, path in (
                ("input_manifest", archive / "input/manifest.json"),
                ("gfs_manifest", archive / "input/gfs_manifest.json"),
                ("fire_snapshot", archive / "input/fire_snapshot.json"),
            ):
                connection.execute(
                    loader.load("simulation/upsert_run_input.sql"),
                    {
                        "run_id": run_uuid,
                        "input_kind": input_kind,
                        "relative_path": path.relative_to(data_root).as_posix(),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                        "metadata": Jsonb({}),
                    },
                ).fetchone()
            scientific_artifacts = [
                ("output_manifest", output_manifest, "application/json", {}),
                (
                    "emission_bundle",
                    archive / "input/emissions.nc",
                    "application/x-netcdf",
                    {"mass_kg_by_species": mass_by_species},
                ),
                (
                    "display_manifest",
                    processed_manifest,
                    "application/json",
                    {"asset_count": len(assets)},
                ),
            ]
            for species in scenario.species:
                member = archive / "transport" / species.lower()
                scientific_artifacts.extend(
                    [
                        (
                            "flexpart_netcdf",
                            next((member / "output").glob("grid_conc_*.nc")),
                            "application/x-netcdf",
                            {"species": species},
                        ),
                        (
                            "model_log",
                            member / "run.log",
                            "text/plain",
                            {"model": "FLEXPART", "species": species},
                        ),
                    ]
                )
            for artifact_kind, path, mime_type, metadata in scientific_artifacts:
                connection.execute(
                    loader.load("simulation/upsert_run_artifact.sql"),
                    {
                        "run_id": run_uuid,
                        "artifact_kind": artifact_kind,
                        "relative_path": path.relative_to(data_root).as_posix(),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                        "mime_type": mime_type,
                        "metadata": Jsonb(metadata),
                        "status": "available",
                    },
                ).fetchone()
            for asset in assets:
                connection.execute(
                    loader.load("simulation/upsert_run_artifact.sql"),
                    {
                        "run_id": run_uuid,
                        "artifact_kind": "display_cog",
                        "relative_path": asset["relative_path"],
                        "sha256": asset["sha256"],
                        "size_bytes": asset["size_bytes"],
                        "mime_type": "image/tiff; application=geotiff; profile=cloud-optimized",
                        "metadata": Jsonb(
                            {
                                "field": asset["field"],
                                "valid_time": asset["valid_time"],
                                "unit": asset["unit"],
                            }
                        ),
                        "status": "available",
                    },
                ).fetchone()
            product_run_id = _publish_catalogue(
                connection,
                loader,
                run_uuid,
                requested_at,
                scenario.start_time,
                assets,
                data_root,
                final_manifest,
                sorted({asset["field"] for asset in assets}),
                output_manifest,
            )
            release_mass_by_species = {
                species: member_manifests[species]["release_summary"][
                    "mass_kg_by_species"
                ][species]
                for species in scenario.species
            }
            mass_balance_residual = max(
                abs(mass_by_species[species] - release_mass_by_species[species])
                for species in scenario.species
            )
            _transition(
                connection,
                loader,
                run_uuid,
                current_state,
                "complete_with_warnings",
                metrics={
                    "event_count": len(events),
                    "asset_count": len(assets),
                    "product_run_id": product_run_id,
                    "mass_kg_by_species": mass_by_species,
                    "particle_count": sum(
                        manifest["release_summary"]["particle_count"]
                        for manifest in member_manifests.values()
                    ),
                    "release_count": sum(
                        manifest["release_summary"]["release_count"]
                        for manifest in member_manifests.values()
                    ),
                    "transport_wall_time_seconds": sum(
                        result["wall_time_seconds"] for result in transport_results.values()
                    ),
                    "publishing_seconds": time.perf_counter() - phase_started,
                    "total_duration_seconds": time.perf_counter() - run_started,
                    "mass_balance_residual_kg": mass_balance_residual,
                    "scientific_output_bytes": _tree_size(archive),
                    "display_output_bytes": sum(asset["size_bytes"] for asset in assets),
                    "temporary_peak_bytes": temporary_peak_bytes,
                },
                warnings=[
                    "Research estimate of primary wildfire emissions; not an official forecast"
                ],
            )
        logger.info(
            "smoke_run_completed",
            extra={
                "simulation_run_id": run_id,
                "task_phase": "complete_with_warnings",
                "species": ",".join(scenario.species),
            },
        )
        return final_manifest
    except Exception as error:
        quarantine = data_root / "quarantine/smoke" / run_id
        quarantine.mkdir(parents=True, exist_ok=True)
        if work.exists():
            shutil.move(work, quarantine / "work")
        elif archive.exists():
            shutil.move(archive, quarantine / "scientific")
        if processed.exists():
            shutil.move(processed, quarantine / "display")
        try:
            with psycopg.connect(database_url, row_factory=dict_row) as connection:
                row = connection.execute(
                    loader.load("simulation/get_run_for_worker.sql"), {"run_id": run_uuid}
                ).fetchone()
                if row and row["status"] == "cancellation_requested":
                    _transition(
                        connection,
                        loader,
                        run_uuid,
                        "cancellation_requested",
                        "cancelled",
                        metrics={
                            "failed_phase": current_state,
                            "total_duration_seconds": time.perf_counter() - run_started,
                        },
                        warnings=["Run cancelled at a model-stage boundary"],
                    )
                    return {"schema_version": 1, "run_id": run_id, "status": "cancelled"}
                if row and row["status"] not in {
                    "complete",
                    "complete_with_warnings",
                    "cancelled",
                    "failed",
                }:
                    _transition(
                        connection,
                        loader,
                        run_uuid,
                        row["status"],
                        "failed",
                        metrics={
                            "failed_phase": current_state,
                            "total_duration_seconds": time.perf_counter() - run_started,
                        },
                        error=error,
                    )
        except Exception:
            pass
        raise
