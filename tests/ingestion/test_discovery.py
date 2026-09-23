from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from weather_ingest.adapters import create_adapter
from weather_ingest.config import load_product_config
from weather_ingest.discovery import discover_available_objects

PROJECT_ROOT = Path(__file__).parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"
RUN_TIME = datetime(2026, 7, 17, 12, tzinfo=UTC)


def _listing(filename: str) -> str:
    return f'<a href="{filename}">{filename}</a> 2026-07-17 13:00 1024\n'


class _Listings:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.requests: list[str] = []

    def get_text(self, url: str) -> str:
        self.requests.append(url)
        if "/12/000/" in url:
            return _listing(self.filename)
        request = httpx.Request("GET", url)
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)


class _MultipleRunListings:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def get_text(self, url: str) -> str:
        self.requests.append(url)
        if "/20260717/" in url and "/12/000/" in url:
            filename = "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"
            return _listing(filename)
        if "/20260717/" in url and "/06/000/" in url:
            filename = "20260717T06Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"
            return _listing(filename)
        request = httpx.Request("GET", url)
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)


def _publish_complete_hour(
    tmp_path: Path, config, run_time: datetime, forecast_hour: int
) -> dict[tuple[datetime, str, int], tuple[str, str]]:
    slots: dict[tuple[datetime, str, int], tuple[str, str]] = {}
    for field in config.fields:
        if not (
            field.download_enabled
            and field.processing_enabled
            and field.availability.includes(forecast_hour)
        ):
            continue
        relative = Path(
            "processed/eccc/hrdps/continental/"
            f"{run_time:%Y%m%dT%H}Z/{field.code}/f{forecast_hour:03d}.tif"
        )
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.touch()
        Path(str(destination) + ".aux.xml").touch()
        slots[(run_time, field.code, forecast_hour)] = (
            relative.as_posix(),
            field.conversion_key,
        )
    return slots


def test_discovery_selects_available_missing_slots_and_ignores_404s(tmp_path: Path) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    filename = "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"
    listings = _Listings(filename)
    adapter = create_adapter(config, listings)

    objects = discover_available_objects(
        config,
        adapter,
        now=datetime(2026, 7, 17, 13, tzinfo=UTC),
        data_root=tmp_path,
        available_slots={},
        limit=512,
    )

    assert [item.parsed.remote.filename for item in objects] == [filename]
    assert any("/12/000/" in url for url in listings.requests)


def test_raqdps_restart_keeps_previous_cycle_when_current_cycle_is_not_published(tmp_path):
    config = load_product_config(CONFIG_ROOT, "raqdps")
    filename = "20260906T12Z_MSC_RAQDPS_NO2_Sfc_RLatLon0.09_PT000H.grib2"
    listings = _Listings(filename)
    objects = discover_available_objects(
        config,
        create_adapter(config, listings),
        now=datetime(2026, 9, 7, 2, tzinfo=UTC),
        data_root=tmp_path,
        available_slots={},
    )
    assert [item.parsed.remote.filename for item in objects] == [filename]
    assert objects[0].run.initialization_time == datetime(2026, 9, 6, 12, tzinfo=UTC)


def test_discovery_does_not_request_a_current_published_slot(tmp_path: Path) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    filename = "20260717T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"
    listings = _Listings(filename)
    adapter = create_adapter(config, listings)
    available_slots = _publish_complete_hour(tmp_path, config, RUN_TIME, 0)

    discover_available_objects(
        config,
        adapter,
        now=RUN_TIME,
        data_root=tmp_path,
        available_slots=available_slots,
        limit=512,
    )

    assert not any("/12/000/" in url for url in listings.requests)


def test_discovery_collects_missing_slots_from_every_candidate_run(
    tmp_path: Path,
) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    listings = _MultipleRunListings()
    adapter = create_adapter(config, listings)

    objects = discover_available_objects(
        config,
        adapter,
        now=datetime(2026, 7, 17, 13, tzinfo=UTC),
        data_root=tmp_path,
        available_slots={},
    )

    assert {item.run.initialization_time for item in objects} == {
        RUN_TIME,
        datetime(2026, 7, 17, 6, tzinfo=UTC),
    }
    assert any("/06/000/" in url for url in listings.requests)


def test_discovery_checks_older_candidates_when_newest_run_is_complete(
    tmp_path: Path,
) -> None:
    config = load_product_config(CONFIG_ROOT, "hrdps")
    listings = _MultipleRunListings()
    adapter = create_adapter(config, listings)
    available_slots = _publish_complete_hour(tmp_path, config, RUN_TIME, 0)

    objects = discover_available_objects(
        config,
        adapter,
        now=datetime(2026, 7, 17, 13, tzinfo=UTC),
        data_root=tmp_path,
        available_slots=available_slots,
    )

    assert {item.run.initialization_time for item in objects} == {
        datetime(2026, 7, 17, 6, tzinfo=UTC)
    }
