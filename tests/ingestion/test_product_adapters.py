import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weather_ingest.adapters.gdps import GdpsAdapter
from weather_ingest.adapters.raqdps import RaqdpsAdapter
from weather_ingest.adapters.rdps import RdpsAdapter
from weather_ingest.cli import run_cli
from weather_ingest.config import load_product_config
from weather_ingest.http_listing import FixtureListingSource
from weather_ingest.inventory import inspect_run
from weather_ingest.models import RemoteObject, RemoteRun

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


@pytest.mark.parametrize(
    ("product", "adapter_type", "domain", "filename", "parameter", "grid", "hour"),
    [
        (
            "raqdps",
            RaqdpsAdapter,
            "north_america",
            "20260716T12Z_MSC_RAQDPS_PM2.5_Sfc_RLatLon0.09_PT003H.grib2",
            "PM2.5",
            "RLatLon0.09",
            3,
        ),
        (
            "rdps",
            RdpsAdapter,
            "north_america",
            "20260716T12Z_MSC_RDPS_AirTemp_AGL-2m_RLatLon0.09_PT084H.grib2",
            "AirTemp",
            "RLatLon0.09",
            84,
        ),
        (
            "gdps",
            GdpsAdapter,
            "global",
            "20260716T12Z_MSC_GDPS_TotalCloudCover_Sfc_LatLon0.15_PT240H.grib2",
            "TotalCloudCover",
            "LatLon0.15",
            240,
        ),
    ],
)
def test_current_product_filenames_parse_to_semantic_identity(
    product,
    adapter_type,
    domain,
    filename,
    parameter,
    grid,
    hour,
) -> None:
    fixtures = PROJECT_ROOT / f"tests/fixtures/{product}/listings"
    adapter = adapter_type(
        load_product_config(CONFIG_ROOT, product), FixtureListingSource(fixtures)
    )
    remote = RemoteObject(f"https://dd.weather.gc.ca/archive/{filename}", filename)

    parsed = adapter.parse_object(remote)

    assert parsed.parameter == parameter
    assert parsed.grid == grid
    assert parsed.forecast_hour == hour
    assert parsed.domain_code == domain
    assert adapter.canonical_object_key(remote).startswith(
        f"eccc/{product}/{domain}/20260716T12Z/f{hour:03d}/"
    )


def test_gdps_segmented_schedule_matches_published_cadence() -> None:
    config = load_product_config(CONFIG_ROOT, "gdps")
    hours = config.forecast_hours.values()

    assert len(hours) == 137
    assert hours[:3] == (0, 1, 2)
    assert 84 in hours
    assert 85 not in hours
    assert 86 not in hours
    assert hours[-3:] == (234, 237, 240)


def test_raqdps_inventory_enables_pollutants_and_flags_unmapped_products() -> None:
    config = load_product_config(CONFIG_ROOT, "raqdps")
    adapter = RaqdpsAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/raqdps/listings")
    )
    run = RemoteRun("raqdps", "north_america", datetime(2026, 7, 16, 12, tzinfo=UTC))

    report = inspect_run(adapter, run, forecast_hours=(0, 1))

    assert report.enabled_object_count == 10
    assert report.unknown_object_count == 2
    assert report.parser_error_count == 0
    assert report.missing_enabled_field_hours == ()


def test_rdps_inventory_uses_live_descriptive_field_names() -> None:
    config = load_product_config(CONFIG_ROOT, "rdps")
    adapter = RdpsAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/rdps/listings")
    )
    run = RemoteRun("rdps", "north_america", datetime(2026, 7, 16, 12, tzinfo=UTC))

    report = inspect_run(adapter, run, forecast_hours=(0, 1))

    assert report.enabled_object_count == 18
    assert report.configured_ignored_count == 0
    assert report.unknown_object_count == 1
    assert report.missing_enabled_field_hours == ()


def test_cli_routes_raqdps_without_requiring_an_explicit_domain(capsys) -> None:
    exit_code = run_cli(
        [
            "--config-root",
            str(CONFIG_ROOT),
            "inspect-source",
            "--product",
            "raqdps",
            "--run",
            "2026-07-16T12:00:00Z",
            "--forecast-hour",
            "0",
            "--listing-fixture",
            str(PROJECT_ROOT / "tests/fixtures/raqdps/listings"),
            "--format",
            "json",
            "--summary-only",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["domain"] == "north_america"
    assert payload["enabled_object_count"] == 5


def test_wrong_producer_is_rejected_even_when_filename_shape_matches() -> None:
    config = load_product_config(CONFIG_ROOT, "raqdps")
    adapter = RaqdpsAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/raqdps/listings")
    )
    filename = "20260716T12Z_MSC_RDPS_PM2.5_Sfc_RLatLon0.09_PT003H.grib2"

    with pytest.raises(ValueError, match="producer"):
        adapter.parse_object(RemoteObject(f"https://dd.weather.gc.ca/{filename}", filename))
