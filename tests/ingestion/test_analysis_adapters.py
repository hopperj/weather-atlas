import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from weather_ingest.adapters.hrdpa import HrdpaAdapter
from weather_ingest.adapters.hrepa import HrepaAdapter
from weather_ingest.adapters.rdpa import RdpaAdapter
from weather_ingest.cli import run_cli
from weather_ingest.cog import build_cog_command_plan
from weather_ingest.config import load_product_config
from weather_ingest.http_listing import FixtureListingSource
from weather_ingest.inventory import inspect_run
from weather_ingest.models import RemoteObject, RemoteRun
from weather_ingest.storage import (
    canonical_source_key,
    processed_relative_path,
    raw_relative_path,
)

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


@pytest.mark.parametrize(
    ("product", "kind", "domain", "format_name", "field_count"),
    [
        ("hrdpa", "analysis", "continental", "grib2", 4),
        ("rdpa", "analysis", "north_america", "grib2", 4),
        ("hrepa", "ensemble_analysis", "canada_northern_us", "nc", 3),
    ],
)
def test_analysis_configs_are_strict_about_time_and_format(
    product: str,
    kind: str,
    domain: str,
    format_name: str,
    field_count: int,
) -> None:
    config = load_product_config(CONFIG_ROOT, product)

    assert config.kind == kind
    assert config.domain(domain).grid in {"RLatLon0.0225", "RLatLon0.09"}
    assert config.domain(domain).grid_width is not None
    assert config.domain(domain).grid_height is not None
    assert config.source_formats == (format_name,)
    assert config.forecast_hours.values() == (0,)
    assert config.analysis_timing is not None
    assert len(config.fields) == field_count
    assert all(field.analysis is not None for field in config.fields)
    if product == "hrepa":
        assert all(field.processing_enabled for field in config.fields)
        assert all(field.display_enabled for field in config.fields)


def test_hrdpa_filename_maps_to_past_accumulation_interval() -> None:
    config = load_product_config(CONFIG_ROOT, "hrdpa")
    adapter = HrdpaAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/hrdpa/listings")
    )
    filename = "20260716T12Z_MSC_HRDPA-Prelim_APCP-Accum6h_Sfc_RLatLon0.0225_PT0H.grib2"

    parsed = adapter.parse_object(
        RemoteObject(f"https://dd.weather.gc.ca/archive/{filename}", filename)
    )

    assert parsed.time_kind == "analysis"
    assert parsed.forecast_hour == 0
    assert parsed.valid_time == datetime(2026, 7, 16, 12, tzinfo=UTC)
    assert parsed.interval_start == datetime(2026, 7, 16, 6, tzinfo=UTC)
    assert parsed.interval_end == parsed.valid_time
    assert parsed.accumulation_hours == 6
    assert parsed.analysis_revision == "preliminary"
    assert adapter.field_for(parsed).code == "precipitation_6h_preliminary"
    assert adapter.canonical_object_key(parsed.remote).startswith(
        "eccc/hrdpa/continental/valid_20260716T12Z/accum_06h/preliminary/"
    )
    assert canonical_source_key(parsed).startswith(
        "eccc/hrdpa/continental/valid_20260716T12Z/a006h/preliminary/"
    )
    field = adapter.field_for(parsed)
    assert field is not None
    assert raw_relative_path(parsed).parts[-3:-1] == ("a006h", "preliminary")
    assert processed_relative_path(parsed, field).name == "a006h.tif"


def test_analysis_cog_plan_selects_only_the_precipitation_band() -> None:
    config = load_product_config(CONFIG_ROOT, "hrdpa")
    field = config.field("precipitation_6h_final")

    plan = build_cog_command_plan("source.grib2", "stage.tif.part", "final.tif", field)

    assert len(plan.commands) == 1
    assert plan.commands[0][0] == "gdal_translate"
    assert plan.commands[0][5:7] == ("-b", "1")


def test_24_hour_analysis_is_only_expected_at_06z_and_12z() -> None:
    config = load_product_config(CONFIG_ROOT, "rdpa")
    adapter = RdpaAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/rdpa/listings")
    )
    midnight = RemoteRun("rdpa", "north_america", datetime(2026, 7, 16, 0, tzinfo=UTC))
    noon = RemoteRun("rdpa", "north_america", datetime(2026, 7, 16, 12, tzinfo=UTC))

    assert adapter.expected_manifest(midnight).expected_field_hours == frozenset(
        {("precipitation_6h_preliminary", 0), ("precipitation_6h_final", 0)}
    )
    assert len(adapter.expected_manifest(noon).expected_field_hours) == 4


def test_deterministic_analysis_inventory_classifies_both_revisions() -> None:
    config = load_product_config(CONFIG_ROOT, "hrdpa")
    adapter = HrdpaAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/hrdpa/listings")
    )
    run = RemoteRun("hrdpa", "continental", datetime(2026, 7, 16, 12, tzinfo=UTC))

    report = inspect_run(adapter, run)

    assert report.product_kind == "analysis"
    assert report.inspected_forecast_hours == (0,)
    assert report.enabled_object_count == 4
    assert report.missing_enabled_field_hours == ()
    assert report.estimated_enabled_bytes_per_run is not None
    assert report.estimated_enabled_raw_bytes_per_day is None
    assert {
        item.parsed.analysis_revision
        for item in report.objects
        if item.parsed and item.disposition.value == "enabled"
    } == {"preliminary", "final"}


def test_hrepa_netcdf_files_distinguish_members_and_percentiles() -> None:
    config = load_product_config(CONFIG_ROOT, "hrepa")
    adapter = HrepaAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/hrepa/listings")
    )
    run = RemoteRun(
        "hrepa", "canada_northern_us", datetime(2026, 7, 16, 12, tzinfo=UTC)
    )

    report = inspect_run(adapter, run)

    assert report.product_kind == "ensemble_analysis"
    assert report.enabled_object_count == 3
    assert report.unknown_object_count == 0
    assert report.parser_error_count == 0
    assert report.missing_enabled_field_hours == ()
    assert {item.parsed.data_format for item in report.objects if item.parsed} == {"nc"}
    assert {item.parsed.analysis_revision for item in report.objects if item.parsed} == {
        "ensemble_members",
        "percentile_25",
        "percentile_75",
    }


def test_analysis_cli_exposes_valid_time_and_interval_semantics(capsys) -> None:
    exit_code = run_cli(
        [
            "--config-root",
            str(CONFIG_ROOT),
            "inspect-source",
            "--product",
            "hrepa",
            "--reference-time",
            "2026-07-16T12:00:00Z",
            "--listing-fixture",
            str(PROJECT_ROOT / "tests/fixtures/hrepa/listings"),
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["product_kind"] == "ensemble_analysis"
    assert payload["reference_time_semantics"] == "valid_time"
    assert payload["reference_time"] == "2026-07-16T12:00:00Z"
    assert payload["initialization_time"] is None
    assert payload["analysis_valid_time"] == "2026-07-16T12:00:00Z"
    assert payload["objects"][0]["forecast_hour"] is None
    assert payload["objects"][0]["time_offset"] == 0
    assert payload["objects"][0]["accumulation_hours"] == 6
    assert payload["objects"][0]["interval_start"] == "2026-07-16T06:00:00Z"
    assert payload["objects"][0]["interval_end"] == "2026-07-16T12:00:00Z"


def test_analysis_adapter_rejects_nonzero_forecast_offsets() -> None:
    config = load_product_config(CONFIG_ROOT, "rdpa")
    adapter = RdpaAdapter(
        config, FixtureListingSource(PROJECT_ROOT / "tests/fixtures/rdpa/listings")
    )
    run = RemoteRun("rdpa", "north_america", datetime(2026, 7, 16, 12, tzinfo=UTC))

    with pytest.raises(ValueError, match="do not have forecast lead"):
        adapter.directory_url(run, 6)


@pytest.mark.parametrize("mutation", ["missing_timing", "nonzero_offset"])
def test_analysis_configuration_rejects_forecast_semantics(
    tmp_path: Path, mutation: str
) -> None:
    config_root = tmp_path / "config"
    (config_root / "models").mkdir(parents=True)
    (config_root / "variables").mkdir()
    model = yaml.safe_load((CONFIG_ROOT / "models/hrdpa.yaml").read_text())
    if mutation == "missing_timing":
        del model["analysis_timing"]
    else:
        model["forecast_hours"] = {"start": 0, "end": 1, "step": 1}
    (config_root / "models/hrdpa.yaml").write_text(yaml.safe_dump(model))
    (config_root / "variables/precipitation_analysis.yaml").write_text(
        (CONFIG_ROOT / "variables/precipitation_analysis.yaml").read_text()
    )

    with pytest.raises(ValidationError, match="analysis"):
        load_product_config(config_root, "hrdpa")
