"""Feature-gated four-cycle operational smoke workflow."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.smoke_operational import enqueue_operational_run


def _enabled() -> bool:
    return os.environ.get("SMOKE_OPERATIONAL_ENABLED", "false").lower() in {"1", "true", "yes"}


@dag(
    dag_id="flexpart_smoke_operational",
    schedule="45 5,11,17,23 * * *" if _enabled() else None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["flexpart", "cffeps", "smoke", "operational", "feature-gated"],
)
def smoke_operational():
    @task
    def enqueue() -> dict[str, object]:
        if not _enabled():
            return {
                "status": "disabled",
                "reason": "SMOKE_OPERATIONAL_ENABLED remains false pending scientific evaluation",
            }
        return enqueue_operational_run(
            os.environ["WEATHER_DATABASE_URL"],
            Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data")),
            Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))
            / "smoke/operational.yaml",
        )

    enqueue()


flexpart_smoke_operational = smoke_operational()
