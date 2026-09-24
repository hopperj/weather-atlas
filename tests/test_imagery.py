import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import numpy as np
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from weather_api import imagery
from weather_ingest.imagery import (
    atomic_bytes,
    available_times,
    bounded_get,
    create_cog,
    validate_config,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def test_atomic_payload_publication_preserves_bytes_and_shared_group_access(tmp_path):
    path = tmp_path / "raw" / "frame.png"
    atomic_bytes(path, b"weather-payload")
    assert path.read_bytes() == b"weather-payload"
    assert stat.S_IMODE(path.stat().st_mode) == 0o664
    atomic_bytes(path, b"replacement-payload")
    assert path.read_bytes() == b"replacement-payload"
    assert stat.S_IMODE(path.stat().st_mode) == 0o664
    assert list(path.parent.iterdir()) == [path]


def test_permission_failure_does_not_replace_existing_payload(tmp_path, monkeypatch):
    path = tmp_path / "existing.png"
    path.write_bytes(b"original")

    def denied(*args):
        raise PermissionError("denied")

    monkeypatch.setattr("weather_ingest.imagery.os.fchmod", denied)
    with pytest.raises(PermissionError):
        atomic_bytes(path, b"replacement")
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def capabilities(text, name="RADAR_1KM_RRAI"):
    return f"""<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer>
    <Layer><Name>unrelated</Name><Dimension name="time">2020-01-01T00:00:00Z</Dimension></Layer>
    <Layer><Name>{name}</Name><Dimension name="time">{text}</Dimension></Layer>
    </Layer></Capability></WMS_Capabilities>""".encode()


def test_available_times_filters_future_and_preserves_advertised_gaps():
    xml = capabilities("2026-09-07T11:00:00Z/2026-09-07T11:12:00Z/PT6M,2026-09-07T12:06:00Z")
    assert available_times(xml, "RADAR_1KM_RRAI", NOW, 1) == [
        NOW - timedelta(minutes=60),
        NOW - timedelta(minutes=54),
        NOW - timedelta(minutes=48),
    ]
    assert available_times(xml, "RADAR_1KM_RRAI", NOW + timedelta(hours=3), 1) == []


@pytest.mark.parametrize(
    "dimension",
    [
        "2026-09-07T10:00:00Z/2026-09-07T12:00:00Z/PT0M",
        "2020-01-01T00:00:00Z/2026-09-07T12:00:00Z/PT1S",
        "2026-09-07T12:00:00Z/2026-09-07T11:00:00Z/PT6M",
        "2026-09-07T11:00:00",
    ],
)
def test_invalid_time_dimensions_rejected(dimension):
    with pytest.raises(ValueError):
        available_times(capabilities(dimension), "RADAR_1KM_RRAI", NOW, 3)


def test_unsafe_xml_and_missing_layer_rejected():
    for xml in (b"<!DOCTYPE x><x/>", capabilities("2026-09-07T12:00:00Z", "wrong")):
        with pytest.raises(ValueError):
            available_times(xml, "RADAR_1KM_RRAI", NOW, 3)


def config():
    return dict(
        bounds=[-69, 41, -52, 50],
        width=256,
        height=256,
        lookback_hours=3,
        max_new_frames_per_product=4,
        minimum_free_bytes=0,
        maximum_archive_bytes=1024**3,
        products=["radar_rain"],
    )


def test_ingest_budgets_are_bounded():
    assert validate_config(config())["width"] == 256
    for key, value in (
        ("bounds", [-69, 41, float("nan"), 50]),
        ("width", 100000),
        ("products", ["arbitrary_url"]),
        ("max_new_frames_per_product", 1000),
        ("products", ["radar_rain", "radar_rain"]),
    ):
        with pytest.raises(ValueError):
            validate_config({**config(), key: value})


def png_image(width=256, height=256):
    data = np.zeros((4, height, width), dtype="uint8")
    data[0] = 255
    data[3, :, : width // 2] = 255
    with MemoryFile() as file:
        with file.open(driver="PNG", width=width, height=height, count=4, dtype="uint8") as raster:
            raster.write(data)
        return file.read()


def test_rgb_cog_preserves_pixels_georeferencing_and_transparency(tmp_path):
    path = tmp_path / "frame.tif"
    create_cog(png_image(), path, [-69, 41, -52, 50], 256, 256)
    with rasterio.open(path) as source:
        assert source.count == 4
        assert source.crs.to_epsg() == 4326
        assert tuple(source.bounds) == (-69, 41, -52, 50)
        assert source.read(1)[0, 0] == 255
        assert source.read(4)[0, -1] == 0
        assert source.tags(ns="IMAGE_STRUCTURE")["LAYOUT"] == "COG"
    # Outside coverage returns a transparent tile with no upstream request.
    tile = imagery.render_imagery(path, 3, 7, 7)
    with MemoryFile(tile) as file, file.open() as source:
        assert source.width == 256 and source.read(4).max() == 0


def test_invalid_map_response_never_published(tmp_path):
    path = tmp_path / "frame.tif"
    for data in (b"<ServiceException>missing time</ServiceException>", png_image(32, 32)):
        with pytest.raises(ValueError):
            create_cog(data, path, [-69, 41, -52, 50], 256, 256)
        assert not path.exists()


def test_response_download_is_bounded_and_redirects_not_followed():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 100))
    )
    with pytest.raises(ValueError, match="size bound"):
        bounded_get(client, {}, 10)
    client.close()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "https://untrusted.example"})
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        bounded_get(client, {}, 100)
    client.close()


class FakeRepository:
    def __init__(self, frame_id):
        self.frame_id = frame_id

    async def products(self):
        return [dict(code="radar_rain", name="Radar", kind="radar", attribution="ECCC")]

    async def timeline(self, _code):
        return [
            dict(
                id=self.frame_id,
                valid_time=datetime.now(UTC) - timedelta(hours=2),
                bounds=[-69, 41, -52, 50],
            )
        ]

    async def frame(self, frame_id):
        if frame_id != self.frame_id:
            return None
        return dict(
            id=frame_id,
            relative_path="processed/eccc/imagery/test.tif",
            content_sha256="a" * 64,
            bounds=[-69, 41, -52, 50],
            provenance={},
        )


def test_catalogue_tiles_only_read_registered_local_frames(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(imagery.router)
    frame_id = uuid4()
    app.dependency_overrides[imagery.repository] = lambda: FakeRepository(frame_id)
    monkeypatch.setattr(imagery, "settings", replace(imagery.settings, data_root=tmp_path))
    create_cog(
        png_image(), tmp_path / "processed/eccc/imagery/test.tif", [-69, 41, -52, 50], 256, 256
    )
    client = TestClient(app)
    body = client.get("/api/v1/imagery").json()["items"][0]
    assert body["stale"] is True and len(body["frames"]) == 1
    assert body["frames"][0]["tileUrl"].startswith("/tiles/imagery/")
    url = f"/tiles/imagery/{frame_id}/3/7/7.png"
    tile = client.get(url)
    assert tile.status_code == 200 and tile.headers["content-type"] == "image/png"
    assert client.get(url, headers={"If-None-Match": tile.headers["etag"]}).status_code == 304
    assert client.get(f"/tiles/imagery/{uuid4()}/0/0/0.png").status_code == 404
    assert client.get(f"/tiles/imagery/{frame_id}/1/2/0.png").status_code == 404
    assert client.get("/tiles/imagery/not-a-uuid/0/0/0.png").status_code == 422
    assert client.get(f"/tiles/imagery/{frame_id}/legend.png").status_code == 404


def test_nearest_forecast_is_a_bounded_proximity_match():
    from weather_api.forecast import nearest_region

    regions = [
        dict(id="halifax", latitude=44.65, longitude=-63.57),
        dict(id="sydney", latitude=46.14, longitude=-60.19),
    ]
    result = nearest_region(regions, -63.58, 44.65)
    assert result["region"]["id"] == "halifax"
    assert result["matchKind"] == "nearest_representative_point"
    assert 0 < result["distanceKm"] < 2
    assert nearest_region(regions, 10, 10) is None
    assert nearest_region([], -63, 44) is None


def test_nearest_route_validates_coordinates_and_returns_match(monkeypatch):
    from weather_api import main

    async def outlooks(_now):
        return {"regions": [dict(id="halifax", latitude=44.65, longitude=-63.57)]}

    monkeypatch.setattr(main, "_regional_outlooks", outlooks)
    client = TestClient(main.app)
    assert (
        client.get("/api/v1/forecast/nearest?latitude=44.65&longitude=-63.57").json()["region"][
            "id"
        ]
        == "halifax"
    )
    assert client.get("/api/v1/forecast/nearest?latitude=0&longitude=0").status_code == 404
    for latitude in ("nan", "inf", "91"):
        assert (
            client.get(f"/api/v1/forecast/nearest?latitude={latitude}&longitude=0").status_code
            == 422
        )


def test_ingestion_publishes_once_and_skips_registered_frames(tmp_path, monkeypatch):
    import json

    from weather_ingest import imagery as ingest

    now = datetime.now(UTC)
    xml = capabilities(now.isoformat())
    png = png_image()
    requests = []
    records = {}

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def __iter__(self):
            return iter(self.rows)

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

        def execute(self, sql, parameters=None):
            if "FROM catalogue.imagery_product" in sql:
                return Cursor([{"code": "radar_rain"}])
            if sql.startswith("INSERT"):
                # Database publication only happens after all source and display files exist.
                assert (tmp_path / "data" / parameters["relative_path"]).is_file()
                assert (tmp_path / "data" / parameters["provenance"].obj["raw"]).is_file()
                records[parameters["valid_time"]] = parameters
                return Cursor([])
            if "FROM catalogue.imagery_frame" in sql:
                record = records.get(parameters["valid_time"])
                return Cursor([record] if record else [])
            raise AssertionError(sql)

    def respond(request):
        operation = request.url.params["REQUEST"]
        requests.append(operation)
        if operation == "GetCapabilities":
            return httpx.Response(200, content=xml)
        if operation == "GetMap":
            assert request.url.params["TIME"] == now.isoformat().replace("+00:00", "Z")
            assert request.url.params["CRS"] == "CRS:84"
        return httpx.Response(200, content=png)

    original_client = httpx.Client
    monkeypatch.setattr(ingest.psycopg, "connect", lambda *a, **kw: Connection())
    monkeypatch.setattr(
        ingest.httpx,
        "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config()))
    assert ingest.ingest_imagery(path, tmp_path / "data", "unused")["collected"] == 1
    assert ingest.ingest_imagery(path, tmp_path / "data", "unused")["collected"] == 0
    assert requests.count("GetMap") == 1
    assert requests.count("GetLegendGraphic") == 1
    assert len(records) == 1
