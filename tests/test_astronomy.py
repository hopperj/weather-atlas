import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import astronomy as astro
from fastapi.testclient import TestClient
from weather_api import main
from weather_api.astronomy import (
    ObservingCriteria,
    altitude,
    build_forecast,
    collect_weather,
    dark_intervals,
    dew_point,
    qualify,
    site_zone,
)
from weather_api.forecast import utc_text

NOW = datetime(2026, 10, 19, 16, tzinfo=UTC)
HOUR = timedelta(hours=1)


def weather(cloud=10, wind=5, rain=0):
    rows = [
        {
            "time": utc_text(NOW + h * HOUR),
            "cloudPercent": cloud,
            "windKmh": wind,
            "gustKmh": 10,
            "temperatureC": 10,
            "humidityPercent": 90,
        }
        for h in range(30)
    ]
    amounts = [
        {
            "start": r["time"],
            "end": utc_text(NOW + (i + 1) * HOUR),
            "field": "total_precipitation_1h",
            "mm": rain,
        }
        for i, r in enumerate(rows)
    ]
    return {"runTime": utc_text(NOW - 4 * HOUR), "rows": rows, "rain": amounts, "sample": None}


def test_exact_site_timezone_and_server_events():
    result = build_forecast(
        weather(), -63.57, 44.65, "gdps", NOW, 2, "deep_sky", ObservingCriteria()
    )
    assert result["timeZone"] == "America/Halifax"
    assert result["latitude"] == 44.65 and result["longitude"] == -63.57
    night = result["nights"][0]
    assert night["state"] == "window" and night["windows"]
    assert night["events"]["sunset"].startswith("2026-10-19T21:22")
    assert night["events"]["astronomicalDawn"].startswith("2026-10-20T08:58")
    assert result["preview"] and "seeing" in result["unavailableFields"]
    assert site_zone(-3.52, 50.7).key == "Europe/London"
    observer = astro.Observer(44.65, -63.57, 0)
    for interval in night["darkness"]:
        start = datetime.fromisoformat(interval["start"])
        assert abs(altitude(astro.Body.Sun, observer, start) + 18) < 0.02


def test_no_favourable_window_for_missing_stale_or_out_of_coverage_data():
    data = weather()
    data["rows"] = []
    assert (
        build_forecast(data, -63, 45, "gdps", NOW, 1, "deep_sky", ObservingCriteria())["nights"][0][
            "state"
        ]
        == "insufficient_data"
    )
    for key in ("cloudPercent", "windKmh"):
        data = weather()
        for row in data["rows"]:
            row[key] = None
        assert not build_forecast(data, -63, 45, "gdps", NOW, 1, "deep_sky", ObservingCriteria())[
            "nights"
        ][0]["windows"]
    data = weather()
    data["runTime"] = utc_text(NOW - 25 * HOUR)
    result = build_forecast(data, -63, 45, "gdps", NOW, 7, "deep_sky", ObservingCriteria())
    assert result["stale"] and all(n["state"] == "insufficient_data" for n in result["nights"])


def test_cadence_darkness_and_conservative_limits():
    data = weather()
    a, b = NOW, NOW + 3 * HOUR
    rows = [data["rows"][0], data["rows"][3]]
    windows, state, _ = qualify(rows, data["rain"], [(a, b)], a, b, ObservingCriteria(), True)
    assert state == "window" and windows == [(a, b)]
    rows[1]["cloudPercent"] = 80
    assert qualify(rows, data["rain"], [(a, b)], a, b, ObservingCriteria(), True)[1] == "no_window"
    assert qualify(rows, [], [(a, b)], a, b, ObservingCriteria(), True)[1] == "insufficient_data"
    assert (
        qualify(
            rows,
            data["rain"],
            [(b + HOUR, b + 2 * HOUR)],
            b,
            b + 3 * HOUR,
            ObservingCriteria(),
            True,
        )[1]
        == "insufficient_data"
    )
    assert dew_point(10, 100) == 10
    assert dew_point(10, 0) is None


def test_polar_and_dst_noon_sessions_and_moon_mode():
    observer = astro.Observer(80, 0, 0)
    start = datetime(2026, 6, 21, tzinfo=UTC)
    assert dark_intervals(observer, start, start + 24 * HOUR) == []
    start = datetime(2026, 12, 21, tzinfo=UTC)
    assert dark_intervals(observer, start, start + 24 * HOUR)
    result = build_forecast(
        weather(),
        -63.57,
        44.65,
        "gdps",
        datetime(2026, 10, 31, 18, tzinfo=UTC),
        2,
        "lunar_planetary",
        ObservingCriteria(),
    )
    night = result["nights"][0]
    assert (
        datetime.fromisoformat(night["end"]) - datetime.fromisoformat(night["start"])
    ).total_seconds() == 25 * 3600
    assert result["mode"] == "lunar_planetary"


def test_collector_single_run_native_steps_units_and_no_upstream():
    class Repository:
        async def list_runs(self, product, limit, field):
            return [{"run_time": NOW - 4 * HOUR, "status": "complete"}]

        async def list_times(self, product, run, field):
            return [{"valid_time": NOW + h * HOUR, "forecast_hour": h + 4} for h in (0, 3, 6)]

    async def sample(repo, **query):
        assert query["latitude"] == 44.123 and query["longitude"] == -63.987
        assert query["run_time"] == NOW - 4 * HOUR
        return {"value": 20, "unit": "percent", "sample": {"latitude": 44.1, "longitude": -64}}

    result = asyncio.run(
        collect_weather(Repository(), sample, -63.987, 44.123, "gdps", NOW, NOW + 8 * HOUR, NOW)
    )
    assert len(result["rows"]) == 3
    assert all(r["cloudPercent"] == 20 and r["windKmh"] is None for r in result["rows"])
    assert result["sample"]["latitude"] == 44.1


def test_endpoint_validation_and_missing_weather_still_provides_ephemeris(monkeypatch):
    async def limit(request):
        pass

    async def empty(*args):
        return {"runTime": None, "rows": [], "rain": [], "sample": None}

    monkeypatch.setattr(main, "_enforce_sample_rate_limit", limit)
    monkeypatch.setattr(main, "collect_weather", empty)
    main.app.dependency_overrides[main.get_repository] = lambda: SimpleNamespace()
    try:
        client = TestClient(main.app)
        response = client.get("/api/v1/astronomy/forecast?latitude=44.65&longitude=-63.57&nights=1")
        assert response.status_code == 200
        assert response.json()["nights"][0]["events"]["sunset"]
        assert response.headers["cache-control"] == "private, no-store"
        for query in [
            "latitude=nan&longitude=0",
            "latitude=91&longitude=0",
            "latitude=0&longitude=0&nights=8",
            "latitude=0&longitude=0&mode=fake",
        ]:
            assert client.get("/api/v1/astronomy/forecast?" + query).status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_native_raster_sample_reports_the_actual_cell_not_a_forecast_town(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "cloud.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-64, 46, 0.5, 0.5),
        nodata=-9999,
    ) as dataset:
        dataset.write(np.array([[10, 20], [30, -9999]], dtype="float32"), 1)
    result = main._astronomy_raster_sample(path, -63.9, 45.9)
    assert result["value"] == 10
    assert result["sample"]["longitude"] == -63.75
    assert result["sample"]["latitude"] == 45.75
    assert result["sample"]["pixelSize"] == [0.5, 0.5]
    assert len(result["sample"]["footprint"]) == 4
    assert main._astronomy_raster_sample(path, -63.1, 45.1)["sample"] is None
    assert main._astronomy_raster_sample(path, -80, 30)["value"] is None


def test_criteria_changes_reuse_weather_grids_but_recompute_windows(monkeypatch):
    class Cache:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def setex(self, key, seconds, value):
            assert seconds == 120
            self.values[key] = value

    calls = []

    async def empty(*args):
        calls.append(args)
        return {"runTime": None, "rows": [], "rain": [], "sample": None}

    async def limit(request):
        pass

    monkeypatch.setattr(main, "collect_weather", empty)
    monkeypatch.setattr(main, "_enforce_sample_rate_limit", limit)
    previous = getattr(main.app.state, "redis", None)
    main.app.state.redis = Cache()
    main.app.dependency_overrides[main.get_repository] = lambda: SimpleNamespace()
    try:
        client = TestClient(main.app)
        url = "/api/v1/astronomy/forecast?latitude=44.65&longitude=-63.57&nights=1"
        assert client.get(url).json()["criteria"]["maxCloudPercent"] == 30
        assert client.get(url + "&max_cloud_percent=10").json()["criteria"]["maxCloudPercent"] == 10
        assert len(calls) == 1
    finally:
        main.app.state.redis = previous
        main.app.dependency_overrides.clear()


def test_regional_wind_is_derived_only_from_both_collected_vector_components():
    class Repository:
        async def list_runs(self, product, limit, field):
            return [{"run_time": NOW - 4 * HOUR, "status": "complete"}]

        async def list_times(self, product, run, field):
            return [{"valid_time": NOW, "forecast_hour": 4}]

    async def sample(repo, **query):
        assert query["domain"] == "north_america"
        field = query["field"]
        return {
            "value": -3 if field == "wind_u_10m" else 4 if field == "wind_v_10m" else None,
            "unit": "m/s",
            "sample": None,
        }

    result = asyncio.run(
        collect_weather(Repository(), sample, -64, 45, "rdps", NOW, NOW + HOUR, NOW)
    )
    assert result["rows"][0]["windKmh"] == 18
    assert "windU" not in result["rows"][0]
