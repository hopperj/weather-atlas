from __future__ import annotations

from pathlib import Path

from weather_ingest.adapters import create_adapter
from weather_ingest.amqp_inbox import discover_inbox_objects
from weather_ingest.config import load_product_config

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


class _UnusedListingSource:
    def get_text(self, _url: str) -> str:
        raise AssertionError("inbox discovery must not request a provider listing")


def test_inbox_discovery_returns_deliveries_from_every_model_run(
    tmp_path: Path,
) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    adapter = create_adapter(config, _UnusedListingSource())
    inbox = tmp_path / "amqp" / "inbox" / "model_hrdps"
    inbox.mkdir(parents=True)
    old_name = (
        "20260717T06Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"
    )
    new_names = (
        "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
        "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT001H.grib2",
    )
    (inbox / old_name).write_bytes(b"old")
    for name in new_names:
        (inbox / name).write_bytes(b"new")

    discovered = discover_inbox_objects(
        tmp_path,
        config,
        adapter,
        limit=512,
    )

    assert {item.parsed.remote.filename for item in discovered} == {
        old_name,
        *new_names,
    }
    assert (inbox / old_name).exists()


def test_inbox_discovery_limit_does_not_delete_unprocessed_deliveries(
    tmp_path: Path,
) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    adapter = create_adapter(config, _UnusedListingSource())
    inbox = tmp_path / "amqp" / "inbox"
    inbox.mkdir(parents=True)
    names = (
        "20260717T06Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
        "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
    )
    for name in names:
        (inbox / name).write_bytes(b"payload")

    discovered = discover_inbox_objects(
        tmp_path,
        config,
        adapter,
        limit=1,
    )

    assert len(discovered) == 1
    assert all((inbox / name).exists() for name in names)
