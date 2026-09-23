"""Bounded database-backed worker for interactive FLEXPART smoke runs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.simulation_jobs import claim_next_run, execute_claimed_run


def _enabled(name: str) -> bool:
    return os.environ.get(name, "false").lower() in {"1", "true", "yes"}


@dag(
    dag_id="flexpart_smoke_worker",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["flexpart", "cffeps", "smoke", "interactive"],
)
def smoke_worker():
    @task(pool="flexpart_runs", retries=0, execution_timeout=timedelta(hours=4))
    def claim_and_execute() -> dict[str, object]:
        writes_enabled = _enabled("SIMULATION_WRITES_ENABLED")
        validation_enabled = _enabled("SMOKE_VALIDATION_RUNS_ENABLED")
        if not writes_enabled and not validation_enabled:
            return {"status": "disabled"}
        database_url = os.environ["WEATHER_DATABASE_URL"]
        run_id = claim_next_run(
            database_url,
            allowed_run_kind=None if writes_enabled else "validation",
        )
        if run_id is None:
            return {"status": "idle"}
        result = execute_claimed_run(
            run_id,
            data_root=Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data")),
            config_root=Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config")),
            cffeps_executable=Path(
                os.environ.get("SMOKE_CFFEPS_EXECUTABLE", "/opt/weather/bin/weatherapp-cffeps")
            ),
            flexpart_root=Path(os.environ.get("SMOKE_FLEXPART_ROOT", "/opt/weather/flexpart")),
            flexpart_executable=Path(
                os.environ.get("SMOKE_FLEXPART_EXECUTABLE", "/opt/weather/bin/FLEXPART")
            ),
            database_url=database_url,
        )
        return {"status": "complete", "run_id": run_id, "asset_count": len(result["assets"])}

    claim_and_execute()


flexpart_smoke_worker = smoke_worker()
