"""Frequent ECCC City Page Weather forecast reconciliation."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.eccc_city_forecasts import (
    CityForecastSettings,
    ingest_city_forecasts,
)


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="eccc_city_forecasts_ingest",
    # ECCC publishes the XML at least hourly and may issue amendments sooner.
    # A 15-minute idempotent reconciliation captures those amendments without
    # redownloading unchanged site files.
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["eccc", "citypage-weather", "seven-day", "forecast", "official"],
)
def city_forecast_ingestion():
    @task(
        pool="eccc_downloads",
        retries=4,
        retry_delay=timedelta(minutes=3),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def reconcile_city_forecasts() -> dict[str, object]:
        result = ingest_city_forecasts(
            CityForecastSettings.from_environment(),
            _data_root(),
        )
        logging.getLogger("airflow.task").info(
            "ECCC city forecast collection %s: %d changed sites, "
            "%d source sites, %d sites without a bulletin, "
            "%d normalized regions, valid %s to %s",
            result["status"],
            result["changed_site_count"],
            result["source_site_count"],
            result["unavailable_site_count"],
            result["region_count"],
            result["available_start"],
            result["available_end"],
        )
        return result

    reconcile_city_forecasts()


eccc_city_forecasts_ingest = city_forecast_ingestion()
