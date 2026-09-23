from pathlib import Path

import pytest
from weather_ingest.adapters import ADAPTER_TYPES, create_adapter
from weather_ingest.config import load_product_config
from weather_ingest.orchestration import (
    MAX_MANUAL_REQUEST_BYTES,
    load_ingestion_dag_definitions,
    prepare_manual_batch,
)

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


class _NoListingSource:
    def get_text(self, _url: str) -> str:
        raise AssertionError("manual request validation must not fetch a listing")


ROUTES = {
    "gdps": (
        "global",
        "20260716T12Z_MSC_GDPS_AirTemp_AGL-2m_LatLon0.15_PT000H.grib2",
        "air_temperature_2m",
    ),
    "hrdps": (
        "continental",
        "20260716T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
        "air_temperature_2m",
    ),
    "raqdps": (
        "north_america",
        "20260716T12Z_MSC_RAQDPS_PM2.5_Sfc_RLatLon0.09_PT000H.grib2",
        "pm25_surface",
    ),
    "rdps": (
        "north_america",
        "20260716T12Z_MSC_RDPS_AirTemp_AGL-2m_RLatLon0.09_PT000H.grib2",
        "air_temperature_2m",
    ),
}


def _request(product: str, filename: str, domain: str) -> dict:
    return {
        "product": product,
        "domain": domain,
        "run": "2026-07-16T12:00:00Z",
        "objects": [
            {
                "url": f"https://dd.weather.gc.ca/objects/{filename}",
                "filename": filename,
                "size_bytes": 1_024,
                "size_is_exact": True,
            }
        ],
    }


def test_enabled_configs_generate_supported_grib_dag_ids_and_routes() -> None:
    definitions = load_ingestion_dag_definitions(CONFIG_ROOT)

    assert {definition.dag_id for definition in definitions} == {
        "eccc_gdps_ingest",
        "eccc_hrdpa_ingest",
        "eccc_hrdps_ingest",
        "eccc_hrepa_ingest",
        "eccc_raqdps_ingest",
        "eccc_rdpa_ingest",
        "eccc_rdps_ingest",
    }
    assert {
        definition.product_code: (
            definition.adapter_code,
            definition.domain_code,
            definition.schedule,
            definition.maximum_objects_per_run,
        )
        for definition in definitions
    } == {
        "gdps": ("gdps", "global", "*/15 * * * *", 128),
        "hrdpa": ("hrdpa", "continental", "15 * * * *", 512),
        "hrdps": ("hrdps", "continental", "15 * * * *", 512),
        "hrepa": ("hrepa", "canada_northern_us", "15 * * * *", 512),
        "raqdps": ("raqdps", "north_america", "15 * * * *", 512),
        "rdpa": ("rdpa", "north_america", "15 * * * *", 512),
        "rdps": ("rdps", "north_america", "15 * * * *", 512),
    }


def test_expected_asset_count_includes_every_processing_enabled_field_hour() -> None:
    assert load_product_config(CONFIG_ROOT, "hrdps").expected_processing_asset_count() == 488
    assert load_product_config(CONFIG_ROOT, "raqdps").expected_processing_asset_count() == 365
    assert load_product_config(CONFIG_ROOT, "gdps").expected_processing_asset_count() == 1477
    assert (
        load_product_config(CONFIG_ROOT, "hrdpa").expected_processing_asset_count(
            reference_hour=12
        )
        == 4
    )
    assert (
        load_product_config(CONFIG_ROOT, "hrepa").expected_processing_asset_count(
            reference_hour=12
        )
        == 3
    )


@pytest.mark.parametrize("product", sorted(ROUTES))
def test_manual_batch_routes_each_product_through_its_configured_adapter(product: str) -> None:
    domain, filename, expected_field = ROUTES[product]
    config = load_product_config(CONFIG_ROOT, product)
    adapter = create_adapter(config, _NoListingSource())

    batch = prepare_manual_batch(product, _request(product, filename, domain), config, adapter)

    assert type(adapter) is ADAPTER_TYPES[product]
    assert batch.run.product_code == product
    assert batch.run.domain_code == domain
    assert batch.objects[0].field_code == expected_field
    assert batch.objects[0].parsed.remote.filename == filename


def test_manual_batch_rejects_cross_product_and_duplicate_routing() -> None:
    product = "hrdps"
    domain, filename, _field = ROUTES[product]
    config = load_product_config(CONFIG_ROOT, product)
    adapter = create_adapter(config, _NoListingSource())
    request = _request(product, filename, domain)
    request["product"] = "rdps"

    with pytest.raises(ValueError, match="conf.product"):
        prepare_manual_batch(product, request, config, adapter)

    request["product"] = product
    request["objects"] = request["objects"] * 2
    with pytest.raises(ValueError, match="duplicate source object"):
        prepare_manual_batch(product, request, config, adapter)


def test_manual_batch_caps_serialized_mapping_payload() -> None:
    product = "hrdps"
    domain, filename, _field = ROUTES[product]
    config = load_product_config(CONFIG_ROOT, product)
    adapter = create_adapter(config, _NoListingSource())
    request = _request(product, filename, domain)
    request["objects"][0]["operator_note"] = "x" * MAX_MANUAL_REQUEST_BYTES

    with pytest.raises(ValueError, match="XCom request size"):
        prepare_manual_batch(product, request, config, adapter)


def test_analysis_dag_route_accepts_processing_enabled_grib() -> None:
    product = "hrdpa"
    domain = "continental"
    filename = (
        "20260716T12Z_MSC_HRDPA_APCP-Accum6h_"
        "Sfc_RLatLon0.0225_PT0H.grib2"
    )
    config = load_product_config(CONFIG_ROOT, product)
    adapter = create_adapter(config, _NoListingSource())

    batch = prepare_manual_batch(product, _request(product, filename, domain), config, adapter)

    assert batch.objects[0].field_code == "precipitation_6h_final"
