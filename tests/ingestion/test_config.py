from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from weather_ingest.config import load_product_config

PROJECT_ROOT = Path(__file__).parents[2]


def test_real_hrdps_configuration_is_strict_and_complete() -> None:
    config = load_product_config(PROJECT_ROOT / "config", "hrdps")

    assert config.code == "hrdps"
    assert config.forecast_hours.values() == tuple(range(49))
    assert config.domain("continental").grid == "RLatLon0.0225"
    assert (
        config.domain("continental").grid_width,
        config.domain("continental").grid_height,
    ) == (2540, 1290)
    assert config.field("air_temperature_2m").source.parameter == "TMP"
    assert [field.code for field in config.fields if field.download_enabled] == [
        "air_temperature_2m",
        "relative_humidity_2m",
        "total_cloud_cover",
        "surface_pressure",
        "mean_sea_level_pressure",
        "wind_u_10m",
        "wind_v_10m",
        "wind_gust_10m",
        "visibility_surface",
        "total_precipitation_1h",
    ]


def test_gdps_configuration_exposes_seven_day_public_forecast_fields() -> None:
    config = load_product_config(PROJECT_ROOT / "config", "gdps")

    assert config.discovery.reconciliation_schedule == "*/15 * * * *"
    assert config.discovery.maximum_objects_per_run == 128
    assert config.limits.minimum_free_bytes == 10 * 1024**3
    assert config.field("wind_speed_10m").source.parameter == "WindSpeed"
    assert config.field("total_precipitation_1h").availability.includes(144)
    precipitation_3h = config.field("total_precipitation_3h")
    assert precipitation_3h.display_name == "Total precipitation · 3 hours"
    assert [
        hour
        for hour in config.forecast_hours.values()
        if precipitation_3h.availability.includes(hour)
    ][-3:] == [162, 165, 168]


def test_unknown_configuration_keys_are_rejected(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    models = config_root / "models"
    variables = config_root / "variables"
    models.mkdir(parents=True)
    variables.mkdir()
    source = yaml.safe_load((PROJECT_ROOT / "config/models/hrdps.yaml").read_text())
    source["surprise"] = True
    (models / "hrdps.yaml").write_text(yaml.safe_dump(source))
    (variables / "atmospheric.yaml").write_text("version: 1\nproducts: {hrdps: []}\n")
    (variables / "precipitation.yaml").write_text("version: 1\nproducts: {hrdps: []}\n")

    with pytest.raises(ValidationError, match="surprise"):
        load_product_config(config_root, "hrdps")


def test_product_code_cannot_escape_configuration_root() -> None:
    with pytest.raises(ValueError, match="invalid product code"):
        load_product_config(PROJECT_ROOT / "config", "../secrets")
