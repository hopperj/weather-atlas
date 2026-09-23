from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds
from weather_api import main as weather_api_main
from weather_api.main import _read_wind_vectors, app, get_repository
from weather_api.repository import ResolvedAssetRecord

RUN = datetime(2026, 7, 23, 12, tzinfo=UTC)
VALID = datetime(2026, 7, 23, 18, tzinfo=UTC)


def _write_constant_raster(path: Path, value: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.full((8, 8), value, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(-10, 40, 10, 50, 8, 8),
        nodata=-9999,
    ) as dataset:
        dataset.write(values, 1)


def test_wind_grid_combines_components_into_speed_and_bearing(tmp_path: Path) -> None:
    u_path = tmp_path / "u.tif"
    v_path = tmp_path / "v.tif"
    _write_constant_raster(u_path, 3)
    _write_constant_raster(v_path, 4)

    features = _read_wind_vectors(
        u_path,
        v_path,
        (-8, 41, 8, 49),
        columns=4,
        rows=3,
    )

    assert len(features) == 12
    assert features[0].properties.speed == 5
    assert features[0].properties.bearing == 36.9
    assert features[0].properties.u == 3
    assert features[0].properties.v == 4


def test_wind_vector_endpoint_returns_map_ready_geojson(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_constant_raster(tmp_path / "processed" / "wind-u.tif", 3)
    _write_constant_raster(tmp_path / "processed" / "wind-v.tif", 4)

    class WindCatalogue:
        async def resolve_asset(self, **parameters):
            field = parameters["field"]
            is_u = field == "wind_u_10m"
            return ResolvedAssetRecord(
                asset_id=1 if is_u else 2,
                relative_path=f"processed/wind-{'u' if is_u else 'v'}.tif",
                style_id=1,
                asset_sha256=("a" if is_u else "b") * 64,
                product="hrdps",
                domain="continental",
                run_time=RUN,
                valid_time=VALID,
                forecast_hour=6,
                field=field,
                variable="wind_u" if is_u else "wind_v",
                level="10m_agl",
                unit="m/s",
                bounds=(-10, 40, 10, 50),
                palette_definition={
                    "stops": [
                        {"value": -40, "color": "#000000"},
                        {"value": 40, "color": "#ffffff"},
                    ]
                },
                display_min=-40,
                display_max=40,
            )

    monkeypatch.setattr(
        weather_api_main,
        "settings",
        replace(weather_api_main.settings, data_root=tmp_path),
    )
    app.dependency_overrides[get_repository] = WindCatalogue
    try:
        response = TestClient(app).get(
            "/api/v1/wind-vectors",
            params={
                "product": "hrdps",
                "domain": "continental",
                "run": RUN.isoformat(),
                "valid_time": VALID.isoformat(),
                "west": -8,
                "south": 41,
                "east": 8,
                "north": 49,
                "columns": 4,
                "rows": 3,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["featureCount"] == 12
    assert payload["unit"] == "m/s"
    assert payload["features"][0]["properties"] == {
        "u": 3.0,
        "v": 4.0,
        "speed": 5.0,
        "bearing": 36.9,
    }
