import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from weather_api import main
from weather_api.forecast import utc_text
from weather_api.golf import (
    HOUR,
    GolfLimits,
    assess_day,
    collect_point,
    period_pop,
    playing_windows,
    rain_bounds,
    regional_context,
    scalar_range,
)

NOW = datetime(2026, 9, 16, 0, tzinfo=UTC)
TEE = NOW + 12 * HOUR
WINDOW = {"date": "2026-09-16", "tee": TEE, "valid": True}


def data(wind=10, rain=0, pop=10):
    rows = [
        {"time": utc_text(NOW + h * HOUR), "temperatureC": 20, "windKmh": wind, "gustKmh": 20}
        for h in range(24)
    ]
    amounts = [
        {
            "start": r["time"],
            "end": utc_text(NOW + (h + 1) * HOUR),
            "field": "total_precipitation_1h",
            "mm": rain,
        }
        for h, r in enumerate(rows)
    ]
    context = {
        "stale": False,
        "periods": [{"start": utc_text(NOW), "end": utc_text(NOW + 24 * HOUR), "popPercent": pop}],
    }
    return rows, amounts, context


def test_complete_score_monotonic_round_cap_and_no_probability_claim():
    good = assess_day(WINDOW, *data(), GolfLimits(), NOW, NOW)
    windy = assess_day(WINDOW, *data(wind=40), GolfLimits(), NOW, NOW)
    assert good["state"] == "within" and good["score"] > 50
    assert windy["state"] == "outside" and windy["score"] < 50
    assert "Sustained wind falls outside" in windy["briefingDetail"]
    assert "before, during and after" in windy["briefingDetail"]
    loose = assess_day(WINDOW, *data(wind=40), GolfLimits(maxWindKmh=60), NOW, NOW)
    assert loose["score"] > windy["score"]
    assert good["segments"][0]["start"] == utc_text(TEE - 2 * HOUR)
    assert good["segments"][1]["end"] == utc_text(TEE + 4 * HOUR)
    assert good["segments"][2]["end"] == utc_text(TEE + 5 * HOUR)
    assert good["modelRows"] and good["precipitationIntervals"] and good["regionalPeriods"]


def test_unpublished_pop_keeps_normal_rainfall_assessment_without_disclaimer():
    result = assess_day(WINDOW, *data(pop=None, rain=0.125), GolfLimits(), NOW, NOW)
    assert result["state"] == "within" and result["score"] is not None
    assert result["scoreCoverage"] == "complete"
    assert result["probabilityNote"] is None
    assert result["segments"][1]["rain"]["maximumMm"] == 0.5
    assert all(p["popPercent"] is None for p in result["segments"])
    assert all(
        next(c for c in p["checks"] if c["field"] == "pop")["fit"] is None
        for p in result["segments"]
    )
    assert "cannot" not in result["briefingDetail"]
    assert "Forecast precipitation stays within your chosen amount" in result["briefingDetail"]
    assert all(
        next(c for c in p["checks"] if c["field"] == "pop")["state"] == "not_provided"
        for p in result["segments"]
    )
    # The same 0.5 mm must fail a stricter amount limit, not disappear with PoP.
    wet = assess_day(WINDOW, *data(pop=None, rain=0.125), GolfLimits(maxRainMm=0.25), NOW, NOW)
    assert wet["state"] == "outside" and wet["score"] < 50
    assert "Precipitation amount falls outside" in wet["briefingDetail"]
    assert wet["probabilityNote"] is None
    assert wet["score"] < result["score"]
    dry = assess_day(WINDOW, *data(pop=0), GolfLimits(maxRainMm=0, maxPopPercent=0), NOW, NOW)
    assert dry["state"] == "within"
    assert dry["segments"][1]["rain"]["maximumMm"] == 0
    assert next(c for c in dry["segments"][1]["checks"] if c["field"] == "pop")["fit"] == 100
    assert dry["scoreCoverage"] == "complete" and dry["probabilityNote"] is None


@pytest.mark.parametrize("field", ["temperatureC", "windKmh", "rain"])
def test_missing_core_weather_still_prevents_score(field):
    rows, rain, context = data(pop=None)
    if field == "rain":
        rain = []
    else:
        for row in rows:
            row[field] = None
    result = assess_day(WINDOW, rows, rain, context, GolfLimits(), NOW, NOW)
    assert result["state"] == "incomplete" and result["score"] is None
    assert result["scoreCoverage"] == "none"


def test_known_limit_failures_remain_visible_with_partial_probability():
    result = assess_day(WINDOW, *data(wind=40, pop=None), GolfLimits(), NOW, NOW)
    assert result["state"] == "outside" and result["score"] < 50
    assert result["scoreCoverage"] == "complete"
    assert "Sustained wind falls outside" in result["briefingDetail"]
    rows, rain, context = data()
    context["periods"] = [
        {"start": utc_text(NOW), "end": utc_text(TEE), "popPercent": None},
        {"start": utc_text(TEE), "end": utc_text(NOW + 24 * HOUR), "popPercent": 90},
    ]
    result = assess_day(WINDOW, rows, rain, context, GolfLimits(), NOW, NOW)
    assert result["scoreCoverage"] == "complete" and result["score"] < 50
    assert result["state"] == "outside"
    assert result["segments"][1]["popPercent"] == 90


def test_native_rain_bounds_no_prorating_no_double_counting():
    _, rain, _ = data(rain=1)
    rain += [
        {
            "start": utc_text(NOW + 12 * HOUR),
            "end": utc_text(NOW + 15 * HOUR),
            "field": "total_precipitation_3h",
            "mm": 3,
        }
    ]
    exact = rain_bounds(rain, TEE, TEE + 4 * HOUR)
    assert exact["minimumMm"] == exact["maximumMm"] == 4
    half = rain_bounds(rain, TEE + HOUR / 2, TEE + 4.5 * HOUR)
    assert half["minimumMm"] == 3 and half["maximumMm"] == 5
    missing = [r for r in rain if r["start"] != utc_text(TEE + 3 * HOUR)]
    assert rain_bounds(missing, TEE, TEE + 4 * HOUR) is None
    inputs = list(data(rain=1))
    inputs[1] = rain
    result = assess_day(
        {**WINDOW, "tee": TEE + HOUR / 2}, *inputs, GolfLimits(maxRainMm=4), NOW, NOW
    )
    assert result["score"] is None
    assert result["segments"][1]["rainTimingUncertain"]


def test_three_hour_scalar_interpolation_and_gaps():
    rows = [{"time": utc_text(NOW + h * HOUR), "v": h} for h in (0, 3, 6)]
    assert scalar_range(rows, "v", NOW + HOUR, NOW + 5 * HOUR) == [1, 5]
    assert scalar_range(rows, "v", NOW - HOUR, NOW + HOUR) is None
    assert scalar_range([rows[0], rows[2]], "v", NOW + HOUR, NOW + 5 * HOUR) is None
    assert (
        scalar_range(
            [rows[0], {"time": utc_text(NOW + HOUR), "v": None}, rows[1]], "v", NOW, NOW + 3 * HOUR
        )
        is None
    )


def test_regional_pop_requires_full_coverage_and_nearby_nonstale_bulletin():
    _, _, context = data()
    assert period_pop(context, TEE, TEE + 4 * HOUR) == 10
    assert period_pop({**context, "stale": True}, TEE, TEE + HOUR) is None
    assert period_pop(context, NOW - HOUR, TEE) is None
    region = {
        **context,
        "id": "x",
        "name": "Halifax Metro",
        "locality": "Halifax",
        "longitude": -63.57,
        "latitude": 44.65,
        "issuedAt": utc_text(NOW),
    }
    assert regional_context([region], -63.57, 44.65)["name"] == "Halifax"
    assert regional_context([region], -60, 40) is None
    with_gap = deepcopy(context)
    with_gap["periods"] = [
        {"start": utc_text(TEE), "end": utc_text(TEE + HOUR), "popPercent": 10},
        {"start": utc_text(TEE + 2 * HOUR), "end": utc_text(TEE + 4 * HOUR), "popPercent": 20},
    ]
    assert period_pop(with_gap, TEE, TEE + 4 * HOUR) is None


def test_dst_and_midnight_keep_four_elapsed_hours():
    zone = ZoneInfo("America/Halifax")
    nonexistent = playing_windows(date(2026, 3, 8), time(2, 30), zone, 1)[0]
    assert not nonexistent["valid"]
    ambiguous = playing_windows(date(2026, 11, 1), time(1, 30), zone, 1)[0]
    assert ambiguous["valid"]  # First occurrence; no invented local time.
    windows = playing_windows(date(2026, 9, 16), time(23, 30), zone, 2)
    assert windows[0]["tee"] == datetime(2026, 9, 17, 2, 30, tzinfo=UTC)
    result = assess_day(windows[0], [], [], None, GolfLimits(), NOW, NOW)
    assert result["endTime"] == "2026-09-17T06:30:00Z"


@pytest.mark.parametrize(
    "value",
    [
        {"minTemperatureC": 30, "maxTemperatureC": 20},
        {"maxRainMm": -1},
        {"maxWindKmh": float("nan")},
        {"maxPopPercent": 101},
    ],
)
def test_invalid_limits_rejected(value):
    with pytest.raises(ValidationError):
        GolfLimits(**value)


def test_started_stale_and_refresh_identity():
    args = data()
    a = assess_day(WINDOW, *args, GolfLimits(), NOW, NOW)
    b = assess_day(WINDOW, *args, GolfLimits(), NOW, NOW + HOUR)
    assert a["contentID"] == b["contentID"]
    assert assess_day(WINDOW, *args, GolfLimits(), NOW, TEE)["score"] is None
    stale = assess_day(WINDOW, *args, GolfLimits(), NOW - 25 * HOUR, NOW)
    assert stale["state"] == "stale" and stale["score"] is None


def test_collection_uses_exact_pin_single_run_units_and_actual_rain_intervals():
    calls = []

    class Repo:
        async def list_runs(self, product, limit, field):
            return [
                {"run_time": NOW + HOUR, "status": "complete"},
                {"run_time": NOW - HOUR, "status": "processing"},
                {"run_time": NOW - 12 * HOUR, "status": "complete"},
            ]

        async def list_times(self, product, run, field):
            assert run == NOW - 12 * HOUR
            return [
                {
                    "valid_time": TEE,
                    "forecast_hour": 24,
                    "interval_start": None,
                    "interval_end": None,
                }
            ]

    async def sample(repo, **kwargs):
        calls.append(kwargs)
        assert kwargs["run_time"] == NOW - 12 * HOUR
        assert kwargs["latitude"] == 44.612345 and kwargs["longitude"] == -63.512345
        field = kwargs["field"]
        return SimpleNamespace(
            nodata=False,
            value=10,
            unit="degC"
            if field.startswith("air_")
            else "m/s"
            if field.startswith("wind_")
            else "mm",
        )

    result = asyncio.run(collect_point(Repo(), -63.512345, 44.612345, [WINDOW], NOW, sample))
    assert result["rows"][0]["windKmh"] == 36
    assert result["rows"][0]["temperatureC"] == 10
    assert len(result["rain"]) == 2  # Registered field defines the interval, not shared metadata.
    assert result["rain"][1]["start"] == utc_text(TEE - 3 * HOUR)
    assert len(calls) == 5


def test_endpoint_validation_cache_and_no_regional_dependency(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    class Cache:
        values = {}

        async def get(self, key):
            return self.values.get(key)

        async def setex(self, key, ttl, value):
            assert ttl == 300
            self.values[key] = value

    calls = []

    async def collect(*args):
        calls.append(args)
        rows, rain, _ = data()
        return {"runTime": utc_text(NOW), "rows": rows, "rain": rain}

    async def regions(now):
        raise main.HTTPException(404, "No regional forecast")

    async def rate(request):
        pass

    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "collect_point", collect)
    monkeypatch.setattr(main, "_regional_outlooks", regions)
    monkeypatch.setattr(main, "_enforce_sample_rate_limit", rate)
    monkeypatch.setattr(main.app.state, "redis", Cache(), raising=False)
    main.app.dependency_overrides[main.get_repository] = lambda: object()
    try:
        client = TestClient(main.app)
        params = {
            "latitude": 44.123456,
            "longitude": -63.123456,
            "local_date": "2026-09-16",
            "tee_time": "10:30",
            "time_zone": "America/Halifax",
        }
        response = client.get("/api/v1/golf/outlook", params=params)
        assert response.status_code == 200
        body = response.json()
        assert body["latitude"] == params["latitude"] and len(body["days"]) == 7
        assert body["regionalContext"] is None and body["days"][0]["score"] is not None
        assert body["days"][0]["scoreCoverage"] == "complete"
        assert body["days"][0]["probabilityNote"] is None
        assert response.headers["cache-control"] == "private, no-store"
        assert (
            client.get("/api/v1/golf/outlook", params={**params, "max_wind_kmh": 15}).status_code
            == 200
        )
        assert len(calls) == 1
        for invalid in [
            {"latitude": "nan"},
            {"longitude": 181},
            {"tee_time": "25:00"},
            {"time_zone": "nonsense"},
            {"min_temperature_c": 45},
            {"local_date": "2026-09-14"},
            {"days": 8},
        ]:
            assert (
                client.get("/api/v1/golf/outlook", params={**params, **invalid}).status_code == 422
            )
        assert len(calls) == 1
    finally:
        main.app.dependency_overrides.clear()
