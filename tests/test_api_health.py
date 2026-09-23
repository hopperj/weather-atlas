import json
from dataclasses import replace

from fastapi.testclient import TestClient
from weather_api import main
from weather_api.main import app


def test_liveness_endpoint() -> None:
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "weather-api"


def test_metrics_endpoint_exposes_bounded_http_metrics() -> None:
    client = TestClient(app)
    client.get("/health/live")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "weather_http_requests_total" in response.text
    assert 'service="weather-api"' in response.text


def test_hotspot_endpoint_serves_latest_geojson_with_etag(tmp_path, monkeypatch) -> None:
    latest = tmp_path / "processed" / "nrcan" / "cwfis" / "firem3" / "latest.geojson"
    latest.parent.mkdir(parents=True)
    latest.write_text('{"type":"FeatureCollection","features":[]}\n')
    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=tmp_path))
    client = TestClient(app)

    response = client.get("/api/v1/hotspots")
    cached = client.get(
        "/api/v1/hotspots",
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    assert response.json()["type"] == "FeatureCollection"
    assert cached.status_code == 304


def test_hotspot_endpoints_list_and_serve_archived_dates(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "processed" / "nrcan" / "cwfis" / "firem3"
    for data_date, feature_count, longitude in (
        ("2026-07-20", 17_131, -63.65),
        ("2026-07-21", 2_672, -112.52),
    ):
        year, month, day = data_date.split("-")
        directory = archive / year / month / day
        directory.mkdir(parents=True)
        geojson = directory / "hotspots_viirs.geojson"
        geojson.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "data_date": data_date,
                    "features": [],
                }
            )
        )
        relative = geojson.relative_to(tmp_path).as_posix()
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "provider": "nrcan",
                    "product": "cwfis_firem3_hotspots",
                    "data_date": data_date,
                    "feature_count": feature_count,
                    "first_observation": f"{data_date}T01:00:00Z",
                    "last_observation": f"{data_date}T23:00:00Z",
                    "bbox": [-140.0, 25.0, longitude, 68.0],
                    "geojson": {
                        "relative_path": relative,
                        "size_bytes": geojson.stat().st_size,
                    },
                }
            )
        )

    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=tmp_path))
    client = TestClient(app)

    dates = client.get("/api/v1/hotspots/dates")
    archived = client.get("/api/v1/hotspots?date=2026-07-20")
    missing = client.get("/api/v1/hotspots?date=2026-07-19")

    assert dates.status_code == 200
    assert dates.json()["availableStart"] == "2026-07-20"
    assert dates.json()["availableEnd"] == "2026-07-21"
    assert [item["featureCount"] for item in dates.json()["items"]] == [
        17_131,
        2_672,
    ]
    assert archived.status_code == 200
    assert archived.headers["x-hotspot-data-date"] == "2026-07-20"
    assert archived.json()["data_date"] == "2026-07-20"
    assert missing.status_code == 404


def test_city_forecast_endpoint_selects_requested_period(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "processed" / "eccc" / "citypage_weather" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "schema_version": 1,
                "provider": "eccc",
                "product": "citypage_weather",
                "generated_at": "2026-07-28T19:10:00Z",
                "issued_at": "2026-07-28T19:05:00Z",
                "available_start": "2026-07-28T19:00:00Z",
                "available_end": "2026-08-04T21:00:00Z",
                "attribution": "Environment and Climate Change Canada",
                "license_url": "https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt",
                "features": [
                    {
                        "type": "Feature",
                        "id": "halifax",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-63.57, 44.65],
                        },
                        "properties": {
                            "area_id": "halifax",
                            "name": "Halifax Metro",
                            "province": "NS",
                            "issued_at": "2026-07-28T19:05:00Z",
                            "source_site": "s0000318",
                            "periods": [
                                {
                                    "period": "Tuesday night",
                                    "valid_start": "2026-07-28T19:00:00Z",
                                    "valid_end": "2026-07-29T09:00:00Z",
                                    "temperature_c": 17,
                                    "temperature_class": "low",
                                    "relative_humidity_percent": 95,
                                    "pop_percent": 80,
                                    "precipitation_amount": "10–20 mm",
                                    "condition": "Rain",
                                }
                            ],
                        },
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=tmp_path))
    client = TestClient(app)

    response = client.get(
        "/api/v1/city-forecasts",
        params={"valid_time": "2026-07-29T00:00:00Z"},
    )
    cached = client.get(
        "/api/v1/city-forecasts",
        params={"valid_time": "2026-07-29T00:00:00Z"},
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert response.status_code == 200
    assert response.headers["x-forecast-source"] == "ECCC City Page Weather"
    assert response.json()["featureCount"] == 1
    properties = response.json()["features"][0]["properties"]
    assert properties["temperatureC"] == 17
    assert properties["relativeHumidityPercent"] == 95
    assert properties["popPercent"] == 80
    assert properties["precipitationAmount"] == "10–20 mm"
    assert cached.status_code == 304
