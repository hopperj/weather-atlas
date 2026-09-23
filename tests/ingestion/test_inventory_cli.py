import json
from datetime import UTC, datetime
from pathlib import Path

from weather_ingest.adapters.hrdps import HrdpsAdapter
from weather_ingest.cli import run_cli
from weather_ingest.config import load_product_config
from weather_ingest.http_listing import FixtureListingSource
from weather_ingest.inventory import inspect_run
from weather_ingest.models import RemoteRun

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURES = PROJECT_ROOT / "tests/fixtures/hrdps/listings"


def test_inventory_classifies_every_object_and_estimates_storage() -> None:
    config = load_product_config(PROJECT_ROOT / "config", "hrdps")
    adapter = HrdpsAdapter(config, FixtureListingSource(FIXTURES))
    run = RemoteRun("hrdps", "continental", datetime(2026, 7, 16, 12, tzinfo=UTC))

    report = inspect_run(adapter, run, forecast_hours=(0, 1))

    assert report.remote_object_count == 20
    assert report.enabled_object_count == 18
    assert report.configured_ignored_count == 0
    assert report.unknown_object_count == 1
    assert report.parser_error_count == 1
    assert report.missing_enabled_field_hours == ()
    assert report.estimated_enabled_bytes_per_run is not None
    assert report.estimated_enabled_raw_bytes_per_day == (
        report.estimated_enabled_bytes_per_run * 4
    )


def test_inventory_cli_can_run_entirely_from_saved_listings(capsys) -> None:
    exit_code = run_cli(
        [
            "--config-root",
            str(PROJECT_ROOT / "config"),
            "inspect-source",
            "--product",
            "hrdps",
            "--run",
            "2026-07-16T12:00:00Z",
            "--forecast-hour",
            "0",
            "--forecast-hour",
            "1",
            "--listing-fixture",
            str(FIXTURES),
            "--format",
            "json",
            "--summary-only",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["product"] == "hrdps"
    assert payload["enabled_object_count"] == 18
    assert "objects" not in payload


def test_build_trigger_cli_emits_bounded_airflow_request(capsys) -> None:
    exit_code = run_cli(
        [
            "--config-root",
            str(PROJECT_ROOT / "config"),
            "build-trigger",
            "--product",
            "hrdps",
            "--run",
            "2026-07-16T12:00:00Z",
            "--forecast-hour",
            "0",
            "--forecast-hour",
            "1",
            "--listing-fixture",
            str(FIXTURES),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["dag_id"] == "eccc_hrdps_ingest"
    assert len(payload["requests"]) == 1
    request = payload["requests"][0]
    assert request["product"] == "hrdps"
    assert request["domain"] == "continental"
    assert request["run"] == "2026-07-16T12:00:00Z"
    assert len(request["objects"]) == 18
    assert all(
        set(item) == {"url", "filename", "size_bytes", "size_is_exact"}
        for item in request["objects"]
    )
