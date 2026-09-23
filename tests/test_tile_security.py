import time
from pathlib import Path

from fastapi.testclient import TestClient
from weather_common.layer_tokens import LayerTokenPayload, create_layer_token
from weather_tiles.main import app, settings
from weather_tiles.repository import RenderableAsset


def test_tile_service_does_not_expose_arbitrary_cog_url() -> None:
    response = TestClient(app).get("/cog/tiles/0/0/0?url=file:///etc/passwd")
    assert response.status_code == 404


def test_tile_metrics_endpoint_is_available_for_internal_scraping() -> None:
    client = TestClient(app)
    client.get("/health/live")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "weather_http_request_duration_seconds" in response.text
    assert 'service="tile-api"' in response.text


def test_unknown_well_formed_layer_token_is_rejected() -> None:
    token = "a" * 20
    response = TestClient(app).get(f"/tiles/v1/{token}/0/0/0.webp")
    assert response.status_code == 404


class FakeTileRepository:
    async def get_renderable_asset(self, **_parameters) -> RenderableAsset:
        return RenderableAsset(
            asset_id=1,
            relative_path="processed/fixture.tif",
            asset_sha256="a" * 64,
            style_id=2,
            resampling_method="bilinear",
            palette_definition={
                "stops": [
                    {"value": -40, "color": "#000000"},
                    {"value": 40, "color": "#ffffff"},
                ]
            },
        )


def test_signed_token_can_only_render_its_registered_format(monkeypatch) -> None:
    render_parameters = {}
    token = create_layer_token(
        LayerTokenPayload(
            asset_id=1,
            style_id=2,
            asset_sha256="a" * 64,
            display_min=-40,
            display_max=40,
            output_format="webp",
            expires_at=int(time.time()) + 300,
            opacity_cutoff=20,
            palette_mode="relative",
        ),
        settings.layer_token_secret,
    )
    app.state.tile_repository = FakeTileRepository()
    monkeypatch.setattr("weather_tiles.main.resolve_asset_path", lambda *_args: Path("fixture.tif"))
    def render_tile(*_args, **parameters):
        render_parameters.update(parameters)
        return b"RIFF"

    monkeypatch.setattr("weather_tiles.main.render_registered_tile", render_tile)
    try:
        client = TestClient(app)
        accepted = client.get(f"/tiles/v1/{token}/0/0/0.webp")
        rejected = client.get(f"/tiles/v1/{token}/0/0/0.png")
    finally:
        del app.state.tile_repository

    assert accepted.status_code == 200
    assert accepted.headers["content-type"] == "image/webp"
    assert "immutable" in accepted.headers["cache-control"]
    assert render_parameters["opacity_cutoff"] == 20
    assert render_parameters["palette_mode"] == "relative"
    assert rejected.status_code == 404
