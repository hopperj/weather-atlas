from datetime import UTC, datetime
from pathlib import Path

import pytest
from weather_ingest.adapters.hrdps import HrdpsAdapter
from weather_ingest.config import load_product_config
from weather_ingest.http_listing import FixtureListingSource, parse_apache_size
from weather_ingest.models import RemoteObject, RemoteRun

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURES = PROJECT_ROOT / "tests/fixtures/hrdps/listings"


def _adapter() -> HrdpsAdapter:
    return HrdpsAdapter(
        load_product_config(PROJECT_ROOT / "config", "hrdps"),
        FixtureListingSource(FIXTURES),
    )


def test_parses_raw_and_weather_element_filenames() -> None:
    adapter = _adapter()
    raw = RemoteObject(
        "https://dd.weather.gc.ca/object",
        "20260716T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT006H.grib2",
    )
    weather_element = RemoteObject(
        "https://dd.weather.gc.ca/object",
        "20260716T12Z_MSC_HRDPS-WEonG_VISIFG_Sfc_RLatLon0.0225_PT024H.grib2",
    )

    parsed_raw = adapter.parse_object(raw)
    parsed_weather = adapter.parse_object(weather_element)

    assert parsed_raw.parameter == "TMP"
    assert parsed_raw.source_level == "AGL-2m"
    assert parsed_raw.valid_time == datetime(2026, 7, 16, 18, tzinfo=UTC)
    assert parsed_weather.producer == "HRDPS-WEonG"
    assert parsed_weather.forecast_hour == 24


def test_archive_and_today_urls_reflect_distinct_server_layouts() -> None:
    adapter = _adapter()
    run = RemoteRun("hrdps", "continental", datetime(2026, 7, 16, 12, tzinfo=UTC))

    assert adapter.directory_url(run, 6) == (
        "https://dd.weather.gc.ca/20260716/WXO-DD/"
        "model_hrdps/continental/2.5km/12/006/"
    )
    assert adapter.directory_url(run, 6, use_today_alias=True) == (
        "https://dd.weather.gc.ca/today/model_hrdps/continental/2.5km/12/006/"
    )


def test_fixture_listing_and_canonical_key_are_deterministic() -> None:
    adapter = _adapter()
    run = RemoteRun("hrdps", "continental", datetime(2026, 7, 16, 12, tzinfo=UTC))

    objects = adapter.list_run_objects(run, forecast_hours=(0,))
    temperature = next(obj for obj in objects if "_TMP_" in obj.filename)

    assert len(objects) == 10
    assert temperature.size_bytes == 3 * 1024**2
    assert temperature.size_is_exact is False
    assert adapter.canonical_object_key(temperature) == (
        "eccc/hrdps/continental/20260716T12Z/f000/" + temperature.filename
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("193", 193), ("3.0K", 3072), ("2.5M", 2_621_440), ("-", None)],
)
def test_apache_size_parsing(value: str, expected: int | None) -> None:
    assert parse_apache_size(value) == expected
