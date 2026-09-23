from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from weather_api.main import app, get_repository, settings
from weather_api.repository import ResolvedAssetRecord
from weather_common.layer_tokens import verify_layer_token

RUN = datetime(2026, 7, 16, 12, tzinfo=UTC)
VALID = datetime(2026, 7, 16, 18, tzinfo=UTC)


class FakeCatalogue:
    async def list_products(self):
        return [
            {
                "code": "hrdps",
                "name": "HRDPS",
                "description": "High-resolution forecast",
                "kind": "forecast",
                "priority": 1,
                "latest_run_time": RUN,
            }
        ]

    async def list_variables(self):
        return [
            {
                "code": "air_temperature_2m_agl",
                "variable_code": "air_temperature",
                "name": "Air temperature",
                "variable_class": "atmosphere",
                "level_code": "2m_agl",
                "level_name": "2 metres above ground",
                "unit": "Cel",
                "products": ["hrdps", "rdps", "gdps"],
            }
        ]

    async def list_domains(self, _product):
        return [{"code": "continental", "name": "Continental", "bounds": [-141, 39, -42, 84]}]

    async def list_fields(self, _product, _run_time=None):
        return [
            {
                "code": "air_temperature_2m_agl",
                "variable_code": "air_temperature",
                "name": "Air temperature",
                "variable_class": "atmosphere",
                "level_code": "2m_agl",
                "level_name": "2 metres above ground",
                "unit": "Cel",
                "palette": [
                    {"value": -40, "color": "#582a9f"},
                    {"value": 40, "color": "#b40426"},
                ],
                "default_min": -40,
                "default_max": 40,
            }
        ]

    async def list_runs(self, _product, _limit, _before=None, _field=None):
        return [{"run_time": RUN, "status": "complete", "available_time_count": 2}]

    async def list_times(self, _product, _run_time, _field=None):
        return [
            {
                "valid_time": VALID,
                "forecast_hour": 6,
                "interval_start": None,
                "interval_end": None,
                "time_kind": "instant",
            }
        ]

    async def list_timeline(
        self,
        _product,
        _domain,
        _field,
        _start_time,
        _end_time,
        _limit,
    ):
        return [
            {
                "run_time": RUN,
                "valid_time": VALID,
                "forecast_hour": 6,
                "interval_start": None,
                "interval_end": None,
                "time_kind": "instant",
            }
        ]

    async def list_ingestion_status(self):
        return [
            {
                "product_code": "hrdps",
                "run_time": RUN,
                "source_status": "complete",
                "processing_status": "complete",
                "is_visible": True,
                "expected_asset_count": 2,
                "discovered_asset_count": 2,
                "downloaded_asset_count": 2,
                "processed_asset_count": 2,
                "failed_asset_count": 0,
                "first_discovered_at": RUN,
                "completed_at": VALID,
            }
        ]

    async def resolve_asset(self, **_parameters):
        return ResolvedAssetRecord(
            asset_id=9,
            relative_path="processed/eccc/hrdps/fixture.tif",
            style_id=3,
            asset_sha256="a" * 64,
            product="hrdps",
            domain="continental",
            run_time=RUN,
            valid_time=VALID,
            forecast_hour=6,
            field="air_temperature_2m_agl",
            variable="air_temperature",
            level="2m_agl",
            unit="Cel",
            bounds=(-141, 39, -42, 84),
            palette_definition={
                "stops": [
                    {"value": -40, "color": "#582a9f"},
                    {"value": 40, "color": "#b40426"},
                ]
            },
            display_min=-40,
            display_max=40,
            data_min=3.3,
            data_max=22.1,
        )


def fake_repository():
    return FakeCatalogue()


def test_catalogue_collections_use_public_camel_case_contract() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        client = TestClient(app)
        products = client.get("/api/v1/products")
        variables = client.get("/api/v1/variables")
        runs = client.get("/api/v1/products/hrdps/runs")
        times = client.get(f"/api/v1/products/hrdps/runs/{RUN.isoformat()}/times")
    finally:
        app.dependency_overrides.clear()

    assert products.status_code == 200
    assert products.json()["items"][0]["latestRunTime"] == "2026-07-16T12:00:00Z"
    assert variables.json()["items"][0]["products"] == ["hrdps", "rdps", "gdps"]
    assert runs.json()["items"][0]["availableTimeCount"] == 2
    assert times.json()["items"][0]["forecastHour"] == 6


def test_run_history_uses_a_bounded_timestamp_cursor() -> None:
    class PagingCatalogue(FakeCatalogue):
        def __init__(self) -> None:
            self.calls = []

        async def list_runs(self, product, limit, before=None, field=None):
            self.calls.append((product, limit, before, field))
            return [
                {
                    "run_time": RUN - timedelta(hours=offset),
                    "status": "complete",
                    "available_time_count": 2,
                }
                for offset in (0, 6, 12)
            ]

    repository = PagingCatalogue()
    app.dependency_overrides[get_repository] = lambda: repository
    before = RUN + timedelta(hours=6)
    try:
        response = TestClient(app).get(
            "/api/v1/products/hrdps/runs",
            params={
                "limit": 2,
                "before": before.isoformat(),
                "field": "air_temperature_2m",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["nextCursor"] == "2026-07-16T06:00:00+00:00"
    assert repository.calls == [
        ("hrdps", 3, before, "air_temperature_2m")
    ]


def test_cross_run_timeline_returns_each_frames_model_run() -> None:
    class TimelineCatalogue(FakeCatalogue):
        def __init__(self) -> None:
            self.calls = []

        async def list_timeline(
            self,
            product,
            domain,
            field,
            start_time,
            end_time,
            limit,
        ):
            self.calls.append((product, domain, field, start_time, end_time, limit))
            return [
                {
                    "run_time": RUN,
                    "valid_time": VALID,
                    "forecast_hour": 6,
                    "interval_start": None,
                    "interval_end": None,
                    "time_kind": "instant",
                },
                {
                    "run_time": RUN + timedelta(hours=6),
                    "valid_time": VALID + timedelta(hours=1),
                    "forecast_hour": 1,
                    "interval_start": None,
                    "interval_end": None,
                    "time_kind": "instant",
                },
            ]

    repository = TimelineCatalogue()
    app.dependency_overrides[get_repository] = lambda: repository
    start = RUN - timedelta(days=7)
    end = RUN
    try:
        response = TestClient(app).get(
            "/api/v1/products/hrdps/timeline",
            params={
                "domain": "continental",
                "field": "air_temperature_2m",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "runTime": "2026-07-16T12:00:00Z",
                "validTime": "2026-07-16T18:00:00Z",
                "forecastHour": 6,
                "intervalStart": None,
                "intervalEnd": None,
                "timeKind": "instant",
            },
            {
                "runTime": "2026-07-16T18:00:00Z",
                "validTime": "2026-07-16T19:00:00Z",
                "forecastHour": 1,
                "intervalStart": None,
                "intervalEnd": None,
                "timeKind": "instant",
            },
        ],
        "truncated": False,
    }
    assert repository.calls == [
        ("hrdps", "continental", "air_temperature_2m", start, end, 11)
    ]


def test_cross_run_timeline_validates_custom_range() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        client = TestClient(app)
        missing_end = client.get(
            "/api/v1/products/hrdps/timeline",
            params={
                "domain": "continental",
                "field": "air_temperature_2m",
                "start": RUN.isoformat(),
            },
        )
        reversed_range = client.get(
            "/api/v1/products/hrdps/timeline",
            params={
                "domain": "continental",
                "field": "air_temperature_2m",
                "start": VALID.isoformat(),
                "end": RUN.isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert missing_end.status_code == 422
    assert missing_end.json()["detail"] == "start and end must be supplied together"
    assert reversed_range.status_code == 422
    assert reversed_range.json()["detail"] == "start must be earlier than end"


def test_layer_resolution_returns_a_signed_tile_url_without_a_path() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        response = TestClient(app).get(
            "/api/v1/layers/resolve",
            params={
                "product": "hrdps",
                "domain": "continental",
                "run": RUN.isoformat(),
                "field": "air_temperature_2m_agl",
                "valid_time": VALID.isoformat(),
                "style": "default",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["tileUrl"].startswith("/tiles/v1/")
    assert "{z}" in body["tileUrl"]
    assert "relative_path" not in body
    assert "relativePath" not in body


def test_layer_resolution_signs_a_valid_custom_display_range() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/layers/resolve",
            params={
                "product": "hrdps",
                "domain": "continental",
                "run": RUN.isoformat(),
                "field": "air_temperature_2m_agl",
                "valid_time": VALID.isoformat(),
                "minimum": -12.5,
                "maximum": 24.5,
            },
        )
        invalid = client.get(
            "/api/v1/layers/resolve",
            params={
                "product": "hrdps",
                "domain": "continental",
                "run": RUN.isoformat(),
                "field": "air_temperature_2m_agl",
                "valid_time": VALID.isoformat(),
                "minimum": 10,
                "maximum": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["legend"] == {
        "minimum": -12.5,
        "maximum": 24.5,
        "palette": [
            {"value": -12.5, "color": "#582a9f", "label": None},
            {"value": 24.5, "color": "#b40426", "label": None},
        ],
    }
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("variable", "data_min", "data_max", "expected", "mode"),
    [
        ("air_temperature", 3.3, 22.1, (0, 25), "relative"),
        ("air_temperature", -18.8, -3.3, (-20, 0), "relative"),
        ("air_temperature", 5, 5, (5, 10), "relative"),
        ("air_temperature", None, None, (-40, 40), "relative"),
        ("air_temperature", float("nan"), 20, (-40, 40), "relative"),
        ("relative_humidity", 3.3, 22.1, (-40, 40), "absolute"),
    ],
)
def test_temperature_auto_scale_binds_actual_stats_palette_and_token(
    variable, data_min, data_max, expected, mode
):
    class StatsCatalogue(FakeCatalogue):
        async def resolve_asset(self, **parameters):
            return replace(
                await super().resolve_asset(**parameters),
                variable=variable, data_min=data_min, data_max=data_max,
            )

    app.dependency_overrides[get_repository] = lambda: StatsCatalogue()
    try:
        response = TestClient(app).get("/api/v1/layers/resolve", params={
            "product": "hrdps", "domain": "continental", "run": RUN.isoformat(),
            "field": "air_temperature_2m_agl", "valid_time": VALID.isoformat(),
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert (body["legend"]["minimum"], body["legend"]["maximum"]) == expected
    token = verify_layer_token(body["token"], settings.layer_token_secret)
    assert (token.display_min, token.display_max) == expected
    assert token.palette_mode == mode
    assert [stop["value"] for stop in body["legend"]["palette"]] == list(expected)


def test_layer_resolution_signs_an_opacity_cutoff() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        response = TestClient(app).get(
            "/api/v1/layers/resolve",
            params={
                "product": "hrdps",
                "domain": "continental",
                "run": RUN.isoformat(),
                "field": "air_temperature_2m_agl",
                "valid_time": VALID.isoformat(),
                "opacity_cutoff": 20,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    token = verify_layer_token(
        response.json()["token"],
        settings.layer_token_secret,
    )
    assert token.opacity_cutoff == 20


def test_ingestion_status_reports_real_latest_run_counts() -> None:
    app.dependency_overrides[get_repository] = fake_repository
    try:
        response = TestClient(app).get("/api/v1/status/ingestion")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    status = response.json()["items"][0]
    assert status["productCode"] == "hrdps"
    assert status["processedAssetCount"] == 2
    assert status["failedAssetCount"] == 0
