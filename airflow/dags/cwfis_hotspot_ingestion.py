"""Daily, idempotent NRCan CWFIS Fire M3 VIIRS hotspot collection."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.cwfis_hotspots import (
    CwfisHotspotSettings,
    ingest_request,
    plan_from_cwfis,
    publish_latest,
)


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="nrcan_cwfis_hotspots_ingest",
    # CWFIS documents Fire M3 as a daily product. Recent archive files normally
    # finalize shortly after 06:00Z, so 07:15Z leaves a conservative buffer.
    schedule="15 7 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["nrcan", "cwfis", "wildfire", "hotspots", "viirs", "daily"],
)
def cwfis_hotspot_ingestion():
    @task(
        retries=4,
        retry_delay=timedelta(minutes=15),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(hours=1),
    )
    def discover_daily_files() -> dict[str, object]:
        settings = CwfisHotspotSettings.from_environment()
        plan = plan_from_cwfis(settings, _data_root())
        logging.getLogger("airflow.task").info(
            "Planned %d missing CWFIS daily hotspot file(s)",
            len(plan["requests"]),
        )
        return plan

    @task
    def requests_for_mapping(plan: dict[str, object]) -> list[dict[str, object]]:
        requests = plan.get("requests")
        if not isinstance(requests, list):
            raise ValueError("CWFIS discovery request list is invalid")
        return requests

    @task(
        pool="nrcan_cwfis_downloads",
        retries=3,
        retry_delay=timedelta(minutes=10),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=45),
    )
    def ingest_daily_file(request: dict[str, object]) -> dict[str, object]:
        result = ingest_request(
            request,
            _data_root(),
            CwfisHotspotSettings.from_environment(),
        )
        logging.getLogger("airflow.task").info(
            "%s %s: %d raw rows, %d VIIRS hotspots",
            "Reused" if result["reused_existing"] else "Downloaded",
            result["data_date"],
            result["raw_row_count"],
            result["feature_count"],
        )
        return result

    @task(trigger_rule="none_failed")
    def publish_latest_snapshot(
        ingested: list[dict[str, object]],
    ) -> dict[str, object]:
        result = publish_latest(ingested, _data_root())
        logging.getLogger("airflow.task").info(
            "CWFIS collection result: %s, %d hotspot(s), %d raw byte(s)",
            result["status"],
            result["feature_count"],
            result["raw_bytes"],
        )
        return result

    plan = discover_daily_files()
    requests = requests_for_mapping(plan)
    ingested = ingest_daily_file.expand(request=requests)
    publish_latest_snapshot(ingested)


nrcan_cwfis_hotspots_ingest = cwfis_hotspot_ingestion()
