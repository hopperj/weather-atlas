import hashlib
from pathlib import Path

import httpx
import pytest
from weather_ingest.adapters.hrdps import HrdpsAdapter
from weather_ingest.config import load_product_config
from weather_ingest.downloader import (
    DownloadError,
    DownloadIntegrityError,
    StreamingDownloader,
)
from weather_ingest.http_listing import FixtureListingSource
from weather_ingest.models import RemoteObject
from weather_ingest.storage import processed_relative_path, raw_relative_path, resolve_under

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURES = PROJECT_ROOT / "tests/fixtures/hrdps/listings"
FILENAME = "20260716T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT006H.grib2"


def _parsed():
    config = load_product_config(PROJECT_ROOT / "config", "hrdps")
    adapter = HrdpsAdapter(config, FixtureListingSource(FIXTURES))
    remote = RemoteObject(f"https://dd.weather.gc.ca/archive/{FILENAME}", FILENAME)
    return config, remote, adapter.parse_object(remote)


def test_deterministic_storage_paths_do_not_contain_database_ids() -> None:
    config, _remote, parsed = _parsed()

    assert raw_relative_path(parsed) == Path(
        "raw/eccc/hrdps/continental/2026/07/16/12/f006", FILENAME
    )
    assert processed_relative_path(parsed, config.field("air_temperature_2m")) == Path(
        "processed/eccc/hrdps/continental/2026/07/16/12/air_temperature_2m/2m_agl/f006.tif"
    )


def test_downloader_streams_hashes_and_atomically_reuses(tmp_path: Path) -> None:
    body = b"fixture-grib-content"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("weather-platform-ingest/")
        return httpx.Response(200, headers={"Content-Length": str(len(body))}, content=body)

    remote = RemoteObject(f"https://dd.weather.gc.ca/archive/{FILENAME}", FILENAME, len(body))
    with StreamingDownloader(tmp_path, transport=httpx.MockTransport(handler)) as downloader:
        first = downloader.download(remote, Path("raw") / FILENAME)
        second = downloader.download(remote, Path("raw") / FILENAME)

    assert first.path.read_bytes() == body
    assert first.sha256 == hashlib.sha256(body).hexdigest()
    assert first.reused_existing is False
    assert second.reused_existing is True
    assert not first.path.with_name(first.path.name + ".part").exists()


def test_rounded_listing_size_is_not_treated_as_exact(tmp_path: Path) -> None:
    body = b"a little larger than the rounded listing value"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(len(body))}, content=body)

    remote = RemoteObject(
        f"https://dd.weather.gc.ca/archive/{FILENAME}",
        FILENAME,
        size_bytes=32,
        size_is_exact=False,
    )
    with StreamingDownloader(tmp_path, transport=httpx.MockTransport(handler)) as downloader:
        result = downloader.download(remote, Path("raw") / FILENAME)

    assert result.size_bytes == len(body)


def test_downloader_atomically_replaces_a_revised_remote_object(tmp_path: Path) -> None:
    previous = b"partial"
    revised = b"complete revised object"
    destination = resolve_under(tmp_path, Path("raw") / FILENAME)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(previous)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(revised))},
            content=revised,
        )

    remote = RemoteObject(
        f"https://dd.weather.gc.ca/archive/{FILENAME}",
        FILENAME,
        size_bytes=len(revised),
    )
    with StreamingDownloader(tmp_path, transport=httpx.MockTransport(handler)) as downloader:
        result = downloader.download(
            remote,
            Path("raw") / FILENAME,
            replace_existing=True,
        )

    assert result.reused_existing is False
    assert result.path.read_bytes() == revised
    assert not destination.with_name(destination.name + ".part").exists()


def test_downloader_rejects_ssrf_and_size_mismatches(tmp_path: Path) -> None:
    malicious = RemoteObject("https://127.0.0.1/internal", "internal")
    with (
        StreamingDownloader(tmp_path) as downloader,
        pytest.raises(DownloadError, match="allowed HTTPS"),
    ):
        downloader.download(malicious, "raw/internal")

    destination = resolve_under(tmp_path, Path("raw") / FILENAME)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"wrong")
    remote = RemoteObject(f"https://dd.weather.gc.ca/archive/{FILENAME}", FILENAME, size_bytes=20)
    with (
        StreamingDownloader(tmp_path) as downloader,
        pytest.raises(DownloadIntegrityError, match="existing file size"),
    ):
        downloader.download(remote, Path("raw") / FILENAME)


def test_storage_resolution_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe and relative"):
        resolve_under(tmp_path, "../outside")
