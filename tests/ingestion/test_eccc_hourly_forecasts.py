from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from weather_ingest.eccc_city_forecasts import citypage_latest_relative_path
from weather_ingest.eccc_hourly_forecasts import (
    HourlyForecastSettings,
    hourly_forecast_latest_relative_path,
    hourly_forecast_manifest_relative_path,
    ingest_hourly_forecasts,
    normalize_hourly_response,
)

NOW = datetime(2026, 9, 27, 12, 20, tzinfo=UTC)
REGION = {
    "area_id": "1b4ba2b5e8cb3eff",
    "name": "Hants County",
    "locality": "Windsor",
    "province": "NS",
    "longitude": -64.14,
    "latitude": 44.99,
}


def provider_payload(
    *,
    province: str = "NS",
    pop: str = "80",
    start: int = 1790514000,
) -> list[dict]:
    return [
        {
            "displayName": "Windsor",
            "province": province,
            "lat": "44.993",
            "lon": "-64.136",
            "distance": "0.0",
            "timezone": "America/Halifax",
            "mtimes": {"HOURLY_FORECAST": 1790510400},
            "hourlyFcst": {
                "hourlyIssuedTimeShrt": "5:00 AM ADT",
                "hourly": [
                    {
                        "epochTime": start + index * 3600,
                        "condition": "Showers" if index < 8 else "Chance of showers",
                        "precip": pop if index < 8 else "30",
                        "temperature": {"metric": str(15 + index % 2)},
                        "feelsLike": {"metric": ""},
                        "iconCode": "12" if index < 8 else "06",
                        "windSpeed": {"metric": "20"},
                        "windDir": "NE",
                        "windGust": {"metric": "40"},
                        "uv": {"index": "2" if index < 8 else ""},
                    }
                    for index in range(24)
                ],
            },
        }
    ]


def write_inventory(data_root, regions=(REGION,)):
    path = data_root / citypage_latest_relative_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "eccc",
                "product": "citypage_weather",
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": region["area_id"],
                        "geometry": {
                            "type": "Point",
                            "coordinates": [region["longitude"], region["latitude"]],
                        },
                        "properties": {
                            "area_id": region["area_id"],
                            "name": region["name"],
                            "locality": region["locality"],
                            "province": region["province"],
                        },
                    }
                    for region in regions
                ],
            }
        )
    )


def test_normalization_retains_official_pop_condition_and_hourly_fields() -> None:
    result = normalize_hourly_response(provider_payload(), REGION, collected_at=NOW)

    assert result["area_id"] == REGION["area_id"]
    assert result["provider_location"] == "Windsor"
    assert result["issued_at"] == "2026-09-27T12:00:00Z"
    assert result["timezone"] == "America/Halifax"
    assert len(result["hours"]) == 24
    assert result["hours"][0] == {
        "valid_time": "2026-09-27T13:00:00Z",
        "condition": "Showers",
        "pop_percent": 80.0,
        "temperature_c": 15.0,
        "feels_like_c": None,
        "icon_code": "12",
        "wind_speed_kmh": 20.0,
        "wind_direction": "NE",
        "wind_gust_kmh": 40.0,
        "uv_index": 2.0,
    }
    assert result["hours"][8]["pop_percent"] == 30


def test_normalization_treats_provider_calm_wind_as_zero() -> None:
    payload = provider_payload()
    payload[0]["hourlyFcst"]["hourly"][0]["windSpeed"]["metric"] = "Calm"
    payload[0]["hourlyFcst"]["hourly"][0]["windGust"]["metric"] = "calm"

    result = normalize_hourly_response(payload, REGION, collected_at=NOW)

    assert result["hours"][0]["wind_speed_kmh"] == 0
    assert result["hours"][0]["wind_gust_kmh"] == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda payload: payload[0].update(province="NB"), "province"),
        (
            lambda payload: payload[0]["hourlyFcst"]["hourly"].pop(),
            "exactly 24",
        ),
        (
            lambda payload: payload[0]["hourlyFcst"]["hourly"][1].update(epochTime=1790514000),
            "unique and consecutive",
        ),
        (
            lambda payload: payload[0]["hourlyFcst"]["hourly"][0].update(precip="110"),
            "invalid numeric",
        ),
    ],
)
def test_normalization_rejects_wrong_location_or_invalid_hour_series(change, message) -> None:
    payload = provider_payload()
    change(payload)
    with pytest.raises(ValueError, match=message):
        normalize_hourly_response(payload, REGION, collected_at=NOW)


def test_ingestion_publishes_latest_history_manifest_and_skips_unchanged_snapshot(
    tmp_path,
) -> None:
    write_inventory(tmp_path)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "weather.gc.ca"
        assert request.url.path.endswith("/44.99000,-64.14000")
        assert request.url.params["type"] == "city"
        return httpx.Response(200, json=provider_payload())

    settings = HourlyForecastSettings(
        maximum_regions=2,
        minimum_free_bytes=0,
        parallel_downloads=1,
    )
    transport = httpx.MockTransport(handler)
    first = ingest_hourly_forecasts(settings, tmp_path, now=NOW, transport=transport)
    second = ingest_hourly_forecasts(settings, tmp_path, now=NOW, transport=transport)

    assert first["status"] == "updated"
    assert second["status"] == "unchanged"
    assert first["region_count"] == 1 and first["hour_count"] == 24
    assert len(requests) == 2
    snapshot = json.loads((tmp_path / hourly_forecast_latest_relative_path()).read_text())
    assert snapshot["provider"] == "eccc"
    assert snapshot["product"] == "hourly_forecast"
    assert snapshot["regions"][0]["hours"][0]["pop_percent"] == 80
    manifest = json.loads((tmp_path / hourly_forecast_manifest_relative_path()).read_text())
    assert manifest["status"] == "unchanged"
    assert manifest["snapshot"]["sha256"]
    history = list((tmp_path / "processed/eccc/hourly_forecast/history").rglob("*.json"))
    assert len(history) == 1


def test_ingestion_requires_the_city_region_inventory(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="City Page"):
        ingest_hourly_forecasts(
            HourlyForecastSettings(minimum_free_bytes=0),
            tmp_path,
            now=NOW,
            transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        )
