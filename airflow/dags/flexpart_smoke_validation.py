"""Validation-only smoke canary; never unlocks interactive or operational writes."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.smoke_cycle_assessment import (
    validation_environment_preflight,
)
from weather_ingest.smoke_operational import enqueue_operational_run


def _enabled() -> bool:
    return os.environ.get("SMOKE_VALIDATION_RUNS_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def _schedule() -> str | None:
    return os.environ.get("SMOKE_VALIDATION_CRON") if _enabled() else None


@dag(
    dag_id="flexpart_smoke_validation",
    schedule=_schedule(),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["flexpart", "cffeps", "smoke", "validation", "canary", "feature-gated"],
)
def smoke_validation():
    @task
    def preflight_validation() -> dict[str, object]:
        if not _enabled():
            return {
                "status": "disabled",
                "reason": "SMOKE_VALIDATION_RUNS_ENABLED is false",
            }
        report = validation_environment_preflight()
        if not report["passed"]:
            raise RuntimeError(
                "validation environment preflight failed; production writes must remain disabled"
            )
        return report

    @task
    def enqueue_validation(_preflight: dict[str, object]) -> dict[str, object]:
        return enqueue_operational_run(
            os.environ["WEATHER_DATABASE_URL"],
            Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data")),
            Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))
            / "smoke/operational.yaml",
            run_kind="validation",
            requested_by="airflow:flexpart_smoke_validation",
            reviewed_release_manifest=Path(os.environ["SMOKE_VALIDATION_RELEASE_MANIFEST"]),
        )

    enqueue_validation(preflight_validation())


flexpart_smoke_validation = smoke_validation()
