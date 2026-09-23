"""Prepared mobile forecasts and independently collected weather observations."""

from datetime import datetime, timedelta

from airflow.sdk import dag, task
from weather_common.settings import Settings


@dag(
    dag_id="weather_forecast_prepare",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["forecast", "history", "widgets"],
)
def forecast_preparation():
    @task(
        pool="eccc_downloads",
        retries=2,
        retry_delay=timedelta(minutes=3),
        execution_timeout=timedelta(minutes=12),
    )
    def prepare():
        from weather_ingest.forecast_insights import prepare_forecasts

        return prepare_forecasts(Settings.from_environment())

    prepare()


@dag(
    dag_id="weather_stations_ingest",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["eccc", "observations", "stations"],
)
def station_collection():
    @task(
        pool="eccc_downloads",
        retries=2,
        retry_delay=timedelta(minutes=2),
        execution_timeout=timedelta(minutes=8),
    )
    def collect():
        from weather_ingest.weather_stations import collect_stations

        return collect_stations(Settings.from_environment())

    collect()


weather_forecast_prepare = forecast_preparation()
weather_stations_ingest = station_collection()


@dag(
    dag_id="weather_insights_retention",
    schedule="27 5 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["forecast", "observations", "retention"],
)
def insight_maintenance():
    @task(retries=1, retry_delay=timedelta(minutes=5), execution_timeout=timedelta(minutes=5))
    def maintain():
        from weather_ingest.insight_retention import maintain_insights

        return maintain_insights(Settings.from_environment(), dry_run=False)

    maintain()


weather_insights_retention = insight_maintenance()
