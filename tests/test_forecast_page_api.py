import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from weather_api import main
from weather_api.forecast import FIELDS, PROVINCES, hourly_outlook, regional_outlooks
from weather_api.repository import CatalogueNotFoundError

NOW = datetime(2026, 9, 6, 12, 20, tzinfo=UTC)
START = NOW.replace(minute=0)
REGION_ID = "0123456789abcdef"
REGION = {"id": REGION_ID, "longitude": -63.57, "latitude": 44.65}


@pytest.fixture
def outlook_file(tmp_path):
    path = tmp_path / main.CITY_FORECAST_SNAPSHOT
    path.parent.mkdir(parents=True)
    period = {
        "period": "Sunday",
        "valid_start": "2026-09-06T09:00:00Z",
        "valid_end": "2026-09-06T21:00:00Z",
        "temperature_c": 22,
        "temperature_class": "high",
        "relative_humidity_percent": 65,
        "pop_percent": 0,
        "precipitation_amount": "0 mm",
        "condition": "Sunny",
    }
    snapshot = {
        "schema_version": 1,
        "type": "FeatureCollection",
        "provider": "eccc",
        "product": "citypage_weather",
        "generated_at": "2026-09-06T12:00:00Z",
        "features": [
            {
                "id": REGION_ID,
                "geometry": {"coordinates": [-63.57, 44.65]},
                "properties": {
                    "area_id": REGION_ID,
                    "name": "Halifax Metro",
                    "locality": "Halifax",
                    "province": "NS",
                    "issued_at": "2026-09-06T12:00:00Z",
                    "periods": [period],
                },
            }
        ],
    }
    path.write_text(json.dumps(snapshot))
    return path


class ForecastCatalogue:
    async def list_timeline(self, product, domain, field, start, end, limit):
        assert (product, domain, field) == ("gdps", "global", "air_temperature_2m")
        assert (start, end, limit) == (START, START + timedelta(hours=71), 72)
        return [
            {"run_time": START, "valid_time": START, "forecast_hour": 0},
            {"run_time": START, "valid_time": START + timedelta(hours=2), "forecast_hour": 2},
            # Invalid future initialization and a 3-hourly tail must not leak in.
            {
                "run_time": START + timedelta(hours=1),
                "valid_time": START + timedelta(hours=3),
                "forecast_hour": 2,
            },
            {
                "run_time": START - timedelta(hours=86),
                "valid_time": START + timedelta(hours=1),
                "forecast_hour": 87,
            },
        ]


def test_hourly_series_retains_72_rows_gaps_units_and_matching_runs():
    calls = []

    async def sample(_repo, **kwargs):
        calls.append(kwargs)
        assert kwargs["run_time"] == START
        assert kwargs["longitude"] == REGION["longitude"]
        key = kwargs["field"]
        if key == "total_precipitation_1h" and kwargs["valid_time"] == START:
            raise CatalogueNotFoundError
        values = {
            "air_temperature_2m": (-3.5, "degC"),
            "relative_humidity_2m": (80, "percent"),
            "total_precipitation_1h": (0, "mm"),
            "wind_speed_10m": (10, "m/s"),
            "wind_gust_10m": (15, "m/s"),
        }
        value, unit = values[key]
        return SimpleNamespace(value=value, unit=unit, nodata=False)

    result = asyncio.run(hourly_outlook(ForecastCatalogue(), REGION, NOW, sample))
    assert len(result["hours"]) == 72
    first, missing, third, future = result["hours"][:4]
    assert first["windKmh"] == 36 and first["gustKmh"] == 54
    assert first["temperatureC"] == -3.5
    assert first["precipitationMm"] is None and first["status"] == "partial"
    assert third["precipitationMm"] == 0 and third["status"] == "complete"
    assert third["precipitationStart"] == "2026-09-06T13:00:00Z"
    assert missing["time"] == "2026-09-06T13:00:00Z"
    assert all(missing[key] is None for key in FIELDS)
    assert missing["runTime"] is None and future["status"] == "missing"
    assert result["availableHours"] == 2 and result["completeHours"] == 1
    assert len(calls) == 10


def test_missing_rasters_wrong_units_and_invalid_values_stay_missing():
    async def sample(_repo, **kwargs):
        field = kwargs["field"]
        if field == "air_temperature_2m":
            raise FileNotFoundError
        unit = next(unit for code, unit, _ in FIELDS.values() if code == field)
        return SimpleNamespace(
            value=150 if field == "relative_humidity_2m" else -1,
            unit="inches" if field == "total_precipitation_1h" else unit,
            nodata=False,
        )

    result = asyncio.run(hourly_outlook(ForecastCatalogue(), REGION, NOW, sample))
    assert result["availableHours"] == 0
    assert all(row["status"] == "missing" for row in result["hours"])


def test_outlook_retains_zero_and_marks_expired_bulletin(outlook_file):
    fresh = regional_outlooks(outlook_file, NOW)["regions"][0]
    assert fresh["name"] == "Halifax Metro"
    assert fresh["locality"] == "Halifax"
    assert fresh["periods"][0]["popPercent"] == 0
    assert not fresh["stale"]
    expired = regional_outlooks(outlook_file, NOW + timedelta(days=10))["regions"][0]
    assert expired["stale"] and expired["periods"] == []


def test_legacy_snapshot_without_locality_remains_readable(outlook_file):
    snapshot = json.loads(outlook_file.read_text())
    snapshot["features"][0]["properties"].pop("locality")
    outlook_file.write_text(json.dumps(snapshot))
    region = regional_outlooks(outlook_file, NOW)["regions"][0]
    assert region["locality"] == region["name"] == "Halifax Metro"


def test_outlook_covers_every_province_and_territory_with_ns_first(outlook_file):
    snapshot = json.loads(outlook_file.read_text())
    for index, province in enumerate(PROVINCES):
        if province == "NS":
            continue
        feature = deepcopy(snapshot["features"][0])
        feature["id"] = feature["properties"]["area_id"] = f"{index:016x}"
        feature["properties"]["province"] = province
        feature["properties"]["name"] = f"Region in {province}"
        snapshot["features"].append(feature)
    outlook_file.write_text(json.dumps(snapshot))
    regions = regional_outlooks(outlook_file, NOW)["regions"]
    assert len(regions) == 13
    assert regions[0]["province"] == "NS"
    assert {region["province"] for region in regions} == set(PROVINCES)
    assert [region["provinceName"] for region in regions[1:]] == sorted(
        name for code, name in PROVINCES.items() if code != "NS"
    )
    for region in regions:
        assert region["provinceName"] == PROVINCES[region["province"]]
        assert region["periods"][0]["temperatureC"] == 22
        assert not region["stale"]


@pytest.mark.parametrize(
    "province,coordinates",
    [("NS", [-63.57, 44.65]), ("BC", [-123.12, 49.28]), ("NU", [-68.52, 63.75])],
)
def test_forecast_routes_missing_unknown_and_72_hours(
    outlook_file, monkeypatch, province, coordinates
):
    snapshot = json.loads(outlook_file.read_text())
    snapshot["features"][0]["properties"]["province"] = province
    snapshot["features"][0]["geometry"]["coordinates"] = coordinates
    outlook_file.write_text(json.dumps(snapshot))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=outlook_file.parents[3]))

    async def sample(_repo, **kwargs):
        assert kwargs["longitude"] == coordinates[0]
        assert kwargs["latitude"] == coordinates[1]
        raise CatalogueNotFoundError

    monkeypatch.setattr(main, "_resolve_and_sample", sample)
    main.app.dependency_overrides[main.get_repository] = lambda: ForecastCatalogue()
    try:
        client = TestClient(main.app)
        regions = client.get("/api/v1/forecast/regions")
        assert regions.status_code == 200
        assert regions.json()["regions"][0]["id"] == REGION_ID
        assert regions.json()["regions"][0]["province"] == province
        assert regions.json()["regions"][0]["provinceName"] == PROVINCES[province]
        hourly = client.get(f"/api/v1/forecast/hourly?area_id={REGION_ID}")
        assert hourly.status_code == 200
        assert len(hourly.json()["hours"]) == 72
        assert client.get("/api/v1/forecast/hourly?area_id=ffffffffffffffff").status_code == 404
        assert client.get("/api/v1/forecast/hourly?area_id=../invalid").status_code == 422
        outlook_file.unlink()
        assert client.get("/api/v1/forecast/regions").status_code == 404
    finally:
        main.app.dependency_overrides.clear()


def test_precipitation_endpoint_caches_by_region_and_bulletin(outlook_file, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    class Cache:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def setex(self, key, ttl, value):
            assert ttl == 300
            self.values[key] = value

    calls = []

    async def estimate(_repo, region, now, _sample):
        calls.append(region)
        return {"regionId": region["id"], "issuedAt": region["issuedAt"], "periods": []}

    async def rate_limit(_request):
        pass

    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=outlook_file.parents[3]))
    monkeypatch.setattr(main, "precipitation_outlook", estimate)
    monkeypatch.setattr(main, "_enforce_sample_rate_limit", rate_limit)
    monkeypatch.setattr(main.app.state, "redis", Cache(), raising=False)
    main.app.dependency_overrides[main.get_repository] = lambda: ForecastCatalogue()
    try:
        client = TestClient(main.app)
        url = f"/api/v1/forecast/precipitation?area_id={REGION_ID}"
        assert client.get(url).status_code == 200
        assert client.get(url).json()["regionId"] == REGION_ID
        assert len(calls) == 1
        snapshot = json.loads(outlook_file.read_text())
        snapshot["features"][0]["properties"]["issued_at"] = "2026-09-06T12:15:00Z"
        outlook_file.write_text(json.dumps(snapshot))
        assert client.get(url).json()["issuedAt"] == "2026-09-06T12:15:00Z"
        assert len(calls) == 2
        # A same-issue amendment to amount/period data must invalidate too.
        snapshot["features"][0]["properties"]["periods"][0]["precipitation_amount"] = None
        outlook_file.write_text(json.dumps(snapshot))
        assert client.get(url).status_code == 200
        assert len(calls) == 3
        assert (
            client.get("/api/v1/forecast/precipitation?area_id=ffffffffffffffff").status_code == 404
        )
        assert client.get("/api/v1/forecast/precipitation?area_id=invalid").status_code == 422
    finally:
        main.app.dependency_overrides.clear()
