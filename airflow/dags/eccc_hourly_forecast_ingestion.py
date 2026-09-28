"""Hourly collection of ECCC's official public 24-hour city forecasts."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.eccc_hourly_forecasts import (
    HourlyForecastSettings,
    ingest_hourly_forecasts,
)


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="eccc_hourly_forecasts_ingest",
    schedule="15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["eccc", "official", "hourly", "forecast", "pop"],
)
def hourly_forecast_ingestion():
    @task(
        pool="eccc_downloads",
        retries=4,
        retry_delay=timedelta(minutes=3),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def reconcile_hourly_forecasts() -> dict[str, object]:
        result = ingest_hourly_forecasts(
            HourlyForecastSettings.from_environment(),
            _data_root(),
        )
        logging.getLogger("airflow.task").info(
            "ECCC official hourly forecast collection %s: %d regions, %d hours, issues %s to %s",
            result["status"],
            result["region_count"],
            result["hour_count"],
            result["source_issued_at_min"],
            result["source_issued_at_max"],
        )
        return result

    reconcile_hourly_forecasts()


eccc_hourly_forecasts_ingest = hourly_forecast_ingestion()
