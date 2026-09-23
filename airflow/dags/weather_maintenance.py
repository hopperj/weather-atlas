"""Explicit, bounded maintenance DAGs for the single-server data store."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from airflow.sdk import dag, get_current_context, task
from weather_ingest.maintenance import (
    MaintenanceError,
    PostgresMaintenanceRepository,
    parse_maintenance_options,
    run_asset_retention,
    run_integrity_audit,
    run_temporary_cleanup,
)


def _run_config() -> dict[str, object]:
    value: Any = get_current_context()["dag_run"].conf or {}
    return value if isinstance(value, dict) else dict(value)


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="weather_asset_retention",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["weather", "maintenance", "retention", "manual"],
)
def asset_retention_dag():
    @task
    def retain_assets_and_sources() -> dict[str, object]:
        options = parse_maintenance_options(_run_config(), operation="retention")
        result = run_asset_retention(
            PostgresMaintenanceRepository(),
            _data_root(),
            execute=options.execute,
            limit=options.limit,
        )
        if result["failure_count"]:
            raise MaintenanceError(
                f"retention encountered {result['failure_count']} failures: "
                f"{result['failures'][:3]}"
            )
        return result

    retain_assets_and_sources()


@dag(
    dag_id="weather_integrity_audit",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["weather", "maintenance", "audit", "read-only"],
)
def integrity_audit_dag():
    @task
    def audit_catalogue_files() -> dict[str, object]:
        options = parse_maintenance_options(_run_config(), operation="integrity")
        result = run_integrity_audit(
            PostgresMaintenanceRepository(),
            _data_root(),
            limit=options.limit,
            verify_checksums=options.verify_checksums,
        )
        if options.fail_on_issue and result["issue_count"]:
            raise MaintenanceError(
                f"integrity audit found {result['issue_count']} issues: "
                f"{result['issues'][:3]}"
            )
        return result

    audit_catalogue_files()


@dag(
    dag_id="weather_cleanup_temporary_files",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["weather", "maintenance", "temporary", "manual"],
)
def temporary_cleanup_dag():
    @task
    def cleanup_temporary_files() -> dict[str, object]:
        options = parse_maintenance_options(
            _run_config(), operation="temporary_cleanup"
        )
        assert options.minimum_age_hours is not None
        result = run_temporary_cleanup(
            _data_root(),
            execute=options.execute,
            limit=options.limit,
            minimum_age_hours=options.minimum_age_hours,
        )
        if result["failure_count"]:
            raise MaintenanceError(
                f"temporary cleanup encountered {result['failure_count']} failures: "
                f"{result['failures'][:3]}"
            )
        return result

    cleanup_temporary_files()


weather_asset_retention = asset_retention_dag()
weather_integrity_audit = integrity_audit_dag()
weather_cleanup_temporary_files = temporary_cleanup_dag()
