"""Idempotent feature-gated creation of an operational smoke run."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from weather_common.db import SqlFileLoader

from weather_ingest.fire_scenarios import SmokeScenarioConfig
from weather_ingest.gfs_profiles import resolve_complete_cycle


def _latest_complete_cycle(data_root: Path) -> tuple[Path, dict[str, Any]]:
    candidates = sorted(
        data_root.glob("raw/noaa/gfs/global_1p00/*/*/*/*/manifest.json"), reverse=True
    )
    for candidate in candidates:
        try:
            payload, _ = resolve_complete_cycle(candidate)
        except (FileNotFoundError, ValueError):
            continue
        initialization = datetime.fromisoformat(
            payload["initialization_time"].replace("Z", "+00:00")
        )
        last = max(
            datetime.fromisoformat(item["valid_time"].replace("Z", "+00:00"))
            for item in payload["files"]
        )
        if last >= initialization + timedelta(hours=24):
            return candidate, payload
    raise FileNotFoundError("no complete 24-hour GFS cycle is available")


def enqueue_operational_run(
    database_url: str,
    data_root: Path,
    config_path: Path,
    loader: SqlFileLoader | None = None,
    *,
    run_kind: str = "operational",
    requested_by: str = "airflow:flexpart_smoke_operational",
    reviewed_release_manifest: Path | None = None,
) -> dict[str, Any]:
    sql = loader or SqlFileLoader()
    if run_kind not in {"operational", "validation"}:
        raise ValueError(f"unsupported smoke run kind: {run_kind}")
    if run_kind == "validation" and os.getenv(
        "SIMULATION_WRITES_ENABLED",
        "false",
    ).lower() in {"1", "true", "yes"}:
        raise ValueError("validation cycles require SIMULATION_WRITES_ENABLED=false")
    release_record = None
    if run_kind == "validation":
        if reviewed_release_manifest is None:
            raise ValueError("validation cycles require a reviewed release manifest")
        release = json.loads(reviewed_release_manifest.read_text())
        if (
            release.get("artifact_type") != "cffeps-flexpart-reviewed-release"
            or release.get("status") != "reviewed_frozen"
            or release.get("production_writes_enabled") is not False
            or release.get("w7_final_review", {}).get("passed") is not True
        ):
            raise ValueError("validation release lacks final independent W7 approval")
        release_record = {
            "path": reviewed_release_manifest.resolve().as_posix(),
            "sha256": hashlib.sha256(reviewed_release_manifest.read_bytes()).hexdigest(),
            "release_id": release["release_id"],
        }
    settings = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if settings.get("schema_version") != 1:
        raise ValueError("unsupported operational smoke configuration")
    if run_kind == "operational":
        emission_registry = yaml.safe_load(
            (config_path.parent / "emission_factors.yaml").read_text(encoding="utf-8")
        )
        if emission_registry.get("review", {}).get("status") != "approved":
            raise ValueError(
                "operational enqueue requires an independently approved emissions registry"
            )
    gfs_manifest, gfs = _latest_complete_cycle(data_root)
    start = datetime.fromisoformat(gfs["initialization_time"].replace("Z", "+00:00"))
    scenario = SmokeScenarioConfig.model_validate(
        {
            "name": settings["scenario_name"],
            "start_time": start,
            "end_time": start + timedelta(hours=24),
            "bbox": settings["bbox"],
            "area_mode": "cffeps_native_growth",
            "fire_weather_mode": settings.get("fire_weather_mode", "automatic_cwfis"),
            "fire_weather": settings.get("fire_weather"),
            "species": settings["species"],
            "uncertainty": settings["uncertainty"],
            "grid_spacing_degrees": settings["grid_spacing_degrees"],
            "particle_budget": settings["particle_budget"],
            "random_seed": settings["random_seed"],
        }
    )
    fire_snapshot = data_root / "derived/smoke/fire-events/latest.json"
    if not fire_snapshot.is_file():
        raise FileNotFoundError("no reconciled fire-event snapshot is available")
    snapshot_sha256 = hashlib.sha256(fire_snapshot.read_bytes()).hexdigest()
    cycle = start.astimezone(UTC).isoformat().replace("+00:00", "Z")
    run_key = hashlib.sha256(
        (
            f"{run_kind}\n{cycle}\n{scenario.config_sha256}\n{snapshot_sha256}\n"
            f"{release_record['sha256'] if release_record else 'operational-registry'}\n"
        ).encode()
    ).hexdigest()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        stored_scenario = connection.execute(
            sql.load("simulation/get_or_create_system_scenario.sql"),
            {"name": scenario.name, "description": settings["description"]},
        ).fetchone()
        revision = connection.execute(
            sql.load("simulation/create_revision.sql"),
            {
                "scenario_id": stored_scenario["id"],
                "canonical_config": Jsonb(scenario.model_dump(mode="json")),
                "config_sha256": scenario.config_sha256,
            },
        ).fetchone()
        connection.execute(sql.load("simulation/lock_queue.sql")).fetchone()
        run = connection.execute(
            sql.load("simulation/create_run.sql"),
            {
                "scenario_revision_id": revision["id"],
                "run_kind": run_kind,
                "requested_by": requested_by,
                "run_key": run_key,
                "random_seed_policy": Jsonb(
                    {
                        "kind": "fixed_per_species",
                        "base_seed": scenario.random_seed,
                        "derivation": "base_plus_flexpart_species_number_v1",
                    }
                ),
                "maximum_queued_runs": int(os.getenv("SMOKE_MAX_QUEUED_RUNS", "5")),
            },
        ).fetchone()
        if run is None:
            raise RuntimeError("the smoke queue is at its configured capacity")
    return {
        "status": run["status"],
        "run_id": str(run["id"]),
        "gfs_cycle": cycle,
        "gfs_manifest": gfs_manifest.relative_to(data_root).as_posix(),
        "fire_snapshot_sha256": snapshot_sha256,
        "scenario_config_sha256": scenario.config_sha256,
        "reviewed_release": release_record,
    }
