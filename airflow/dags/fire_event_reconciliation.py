"""Daily deterministic reconciliation of CWFIS detections into fire events."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task
from weather_ingest.cwfis_cffdrs import enrich_event_snapshot
from weather_ingest.fire_events import build_event_snapshot


def _data_root() -> Path:
    return Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))


def _config_root() -> Path:
    return Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))


@dag(
    dag_id="fire_event_reconcile",
    schedule="0 8 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["wildfire", "cwfis", "events", "smoke", "daily"],
)
def fire_event_reconciliation():
    @task
    def reconcile() -> dict[str, object]:
        root = _data_root()
        candidates = sorted(root.glob("processed/nrcan/cwfis/firem3/*/*/*/hotspots_viirs.geojson"))[
            -3:
        ]
        if not candidates:
            return {"status": "no_hotspot_snapshots"}
        data_dates = [
            json.loads(path.read_text(encoding="utf-8"))["data_date"] for path in candidates
        ]
        snapshot_dir = root / "derived/smoke/fire-events" / max(data_dates)
        snapshot_path = snapshot_dir / "events.json"
        build_event_snapshot(
            candidates,
            _config_root() / "smoke/event_matching.yaml",
            snapshot_path,
        )
        result = enrich_event_snapshot(snapshot_path, root)
        latest = root / "derived/smoke/fire-events/latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        temporary = latest.with_suffix(".json.part")
        shutil.copy2(snapshot_path, temporary)
        os.replace(temporary, latest)
        return {
            "status": "complete",
            "snapshot": snapshot_path.relative_to(root).as_posix(),
            "sha256": result["sha256"],
            "event_count": result["event_count"],
            "detection_count": result["detection_count"],
            "cffdrs_enriched_event_count": result["enriched_event_count"],
            "cffdrs_missing_event_count": result["missing_event_count"],
        }

    reconcile()


fire_event_reconcile = fire_event_reconciliation()
