"""Six-hourly, idempotent NOAA GFS pressure-grid collection for FLEXPART."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.noaa_gfs import (
    GfsIngestionSettings,
    download_and_validate_request,
    plan_from_noaa,
    write_cycle_manifests,
)


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


@dag(
    dag_id="noaa_gfs_ingest",
    # GFS initializes at 00/06/12/18Z. Waiting 5h15m allows the complete
    # configured forecast window to be published before discovery.
    schedule="15 5,11,17,23 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["noaa", "gfs", "grib2", "flexpart", "six-hourly"],
)
def noaa_gfs_ingestion():
    @task(
        retries=3,
        retry_delay=timedelta(minutes=10),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=30),
    )
    def discover_complete_cycles() -> dict[str, object]:
        settings = GfsIngestionSettings.from_environment()
        plan = plan_from_noaa(settings, _data_root())
        logging.getLogger("airflow.task").info(
            "Planned %d GFS object(s) across %d cycle(s) at %s resolution",
            len(plan["requests"]),
            len(plan["cycles"]),
            settings.resolution,
        )
        return plan

    @task
    def requests_for_mapping(plan: dict[str, object]) -> list[dict[str, object]]:
        requests = plan.get("requests")
        if not isinstance(requests, list):
            raise ValueError("GFS discovery request list is invalid")
        return requests

    @task(
        pool="noaa_gfs_downloads",
        retries=4,
        retry_delay=timedelta(minutes=3),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def download_and_validate(request: dict[str, object]) -> dict[str, object]:
        result = download_and_validate_request(
            request,
            _data_root(),
            GfsIngestionSettings.from_environment(),
        )
        logging.getLogger("airflow.task").info(
            "%s and validated %s (%d bytes, %d GRIB messages)",
            "Reused" if result["reused_existing"] else "Downloaded",
            result["filename"],
            result["size_bytes"],
            result["message_count"],
        )
        return result

    @task(trigger_rule="none_failed")
    def publish_manifests(
        plan: dict[str, object], downloaded: list[dict[str, object]]
    ) -> dict[str, object]:
        result = write_cycle_manifests(plan, downloaded, _data_root())
        logging.getLogger("airflow.task").info(
            "GFS collection result: %s, %d file(s), %d byte(s)",
            result["status"],
            result["file_count"],
            result["bytes"],
        )
        return result

    plan = discover_complete_cycles()
    requests = requests_for_mapping(plan)
    downloaded = download_and_validate.expand(request=requests)
    publish_manifests(plan, downloaded)


noaa_gfs_ingest = noaa_gfs_ingestion()

