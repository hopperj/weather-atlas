"""Server-only, bounded radar and satellite image acquisition."""

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="eccc_imagery_ingest",
    schedule="*/6 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["eccc", "radar", "satellite"],
)
def imagery_ingestion():
    @task(
        pool="eccc_downloads",
        retries=2,
        retry_delay=timedelta(minutes=2),
        execution_timeout=timedelta(minutes=15),
    )
    def collect():
        from weather_ingest.imagery import ingest_imagery

        return ingest_imagery(
            Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config")) / "imagery.json",
            Path(os.environ["WEATHER_DATA_ROOT"]),
            os.environ["WEATHER_DATABASE_URL"],
        )

    collect()


eccc_imagery_ingest = imagery_ingestion()
