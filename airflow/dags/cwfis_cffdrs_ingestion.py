"""Daily archived NRCan CWFIS FFMC, DMC, and DC grid collection."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.cwfis_cffdrs import CwfisCffdrsSettings, ingest_recent


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="nrcan_cwfis_cffdrs_ingest",
    # Daily national analyses are archived after the preceding fire-weather day.
    # Run before event reconciliation and retry transient publication delays.
    schedule="35 7 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["wildfire", "cwfis", "cffdrs", "ffmc", "dmc", "dc", "daily"],
)
def cwfis_cffdrs_ingestion():
    @task(retries=2, retry_delay=timedelta(minutes=20))
    def collect() -> dict[str, object]:
        return ingest_recent(
            _data_root(),
            datetime.now(UTC),
            CwfisCffdrsSettings.from_environment(),
        )

    collect()


nrcan_cwfis_cffdrs_ingest = cwfis_cffdrs_ingestion()
