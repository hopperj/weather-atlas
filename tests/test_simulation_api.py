from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from weather_api import main
from weather_api.main import app
from weather_api.smoke_preflight import (
    SmokeAdmissionLimits,
    SmokePreflightError,
    preflight_smoke_scenario,
)
from weather_ingest.fire_scenarios import SmokeScenarioConfig


def scenario_payload() -> dict[str, object]:
    return {
        "name": "API smoke test",
        "description": "bounded",
        "config": {
            "name": "API smoke test",
            "start_time": "2026-07-22T06:00:00Z",
            "end_time": "2026-07-23T06:00:00Z",
            "bbox": [-66, 43, -60, 48],
            "event_ids": ["event-a"],
            "area_mode": "cffeps_native_growth",
            "area_curve": [],
            "fire_weather": {"ffmc": 92, "dmc": 45, "dc": 320},
            "species": ["PM25", "CO", "BC"],
            "uncertainty": "central",
            "grid_spacing_degrees": 0.5,
            "particle_budget": 250000,
            "random_seed": 20260722,
        },
    }


def write_complete_inputs(root: Path, event_id: str = "a" * 24) -> None:
    cycle = root / "raw/noaa/gfs/global_1p00/2026/07/22/06"
    cycle.mkdir(parents=True)
    files = []
    for hour in (0, 24):
        path = cycle / f"gfs.f{hour:03d}"
        content = f"gfs-{hour}".encode()
        path.write_bytes(content)
        files.append(
            {
                "filename": path.name,
                "forecast_hour": hour,
                "valid_time": (
                    datetime(2026, 7, 22, 6, tzinfo=UTC).timestamp() + hour * 3600
                ),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    for item in files:
        item["valid_time"] = datetime.fromtimestamp(item["valid_time"], UTC).isoformat().replace(
            "+00:00", "Z"
        )
    (cycle / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "noaa",
                "product": "gfs",
                "initialization_time": "2026-07-22T06:00:00Z",
                "forecast_hours": [0, 24],
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    snapshot = root / "derived/smoke/fire-events/latest.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": event_id,
                        "first_observed_at": "2026-07-21T18:00:00Z",
                        "last_observed_at": "2026-07-22T05:00:00Z",
                        "longitude": -63.0,
                        "latitude": 45.0,
                        "fuel_types": ["C2"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_smoke_capabilities_use_latest_local_complete_gfs_window(
    tmp_path, monkeypatch
) -> None:
    manifest = tmp_path / "raw/noaa/gfs/global_1p00/2026/07/22/06/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "initialization_time": "2026-07-22T06:00:00Z",
                "files": [
                    {"valid_time": "2026-07-22T06:00:00Z"},
                    {"valid_time": "2026-07-23T06:00:00Z"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, data_root=tmp_path, simulation_writes_enabled=False),
    )

    response = TestClient(app).get("/api/v1/smoke/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "writesEnabled": False,
        "validationRunsEnabled": False,
        "latestCompleteGfsCycle": "2026-07-22T06:00:00Z",
        "availableStart": "2026-07-22T06:00:00Z",
        "availableEnd": "2026-07-23T06:00:00Z",
        "maximumHorizonHours": 24,
        "species": ["PM25", "CO", "BC"],
        "uncertaintyModes": ["low", "central", "high"],
        "gridSpacingDegrees": [0.25, 0.5, 1.0],
        "maximumParticles": 1_000_000,
        "maximumReleaseGroupsPerEventHour": 36,
        "minimumParticlesPerRelease": 50,
        "maximumDomainCells": 50_000,
        "maximumReleases": 20_000,
        "maximumQueuedRuns": 5,
        "maximumStorageBytes": 549_755_813_888,
        "primaryEmissionsOnly": True,
    }


def test_smoke_submission_is_locked_before_repository_access(monkeypatch) -> None:
    monkeypatch.setattr(
        main, "settings", replace(main.settings, simulation_writes_enabled=False)
    )
    response = TestClient(app).post("/api/v1/smoke/scenarios", json=scenario_payload())

    assert response.status_code == 503
    assert "disabled pending local scientific validation" in response.json()["detail"]


def test_fire_event_endpoint_filters_to_bounded_extent(tmp_path, monkeypatch) -> None:
    snapshot = tmp_path / "derived/smoke/fire-events/latest.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "algorithm_version": "event-v1",
                "events": [
                    {
                        "event_id": "a" * 24,
                        "first_observed_at": "2026-07-21T12:00:00Z",
                        "last_observed_at": "2026-07-22T05:00:00Z",
                        "latitude": 45,
                        "longitude": -63,
                        "fuel_types": ["C2"],
                    },
                    {
                        "event_id": "b" * 24,
                        "first_observed_at": "2026-07-21T12:00:00Z",
                        "last_observed_at": "2026-07-22T05:00:00Z",
                        "latitude": 60,
                        "longitude": -110,
                        "fuel_types": ["NF"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "settings", replace(main.settings, data_root=tmp_path))

    response = TestClient(app).get("/api/v1/fire-events?bbox=-66,43,-60,48")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["event_id"] for item in items] == ["a" * 24]
    assert items[0]["model_eligible"] is True


def test_smoke_preflight_verifies_inputs_and_estimates_resources(tmp_path) -> None:
    event_id = "a" * 24
    write_complete_inputs(tmp_path, event_id)
    config = SmokeScenarioConfig.model_validate(
        scenario_payload()["config"]
        | {
            "event_ids": [event_id],
        }
    )

    result = preflight_smoke_scenario(
        tmp_path,
        config,
        SmokeAdmissionLimits(
            maximum_horizon_hours=24,
            maximum_domain_cells=50_000,
            maximum_particles=1_000_000,
            maximum_releases=20_000,
            minimum_free_bytes=0,
        ),
    )

    assert result.gfs_cycle == datetime(2026, 7, 22, 6, tzinfo=UTC)
    assert result.fire_event_count == 1
    assert result.domain_cells == 143
    assert result.estimated_releases == 864
    assert result.particle_count == 250_000
    assert result.estimated_output_bytes >= 64 * 1024**2


def test_smoke_preflight_rejects_missing_frozen_event(tmp_path) -> None:
    write_complete_inputs(tmp_path, "a" * 24)
    config = SmokeScenarioConfig.model_validate(
        scenario_payload()["config"] | {"event_ids": ["b" * 24]}
    )

    try:
        preflight_smoke_scenario(
            tmp_path,
            config,
            SmokeAdmissionLimits(
                maximum_horizon_hours=24,
                maximum_domain_cells=50_000,
                maximum_particles=1_000_000,
                maximum_releases=20_000,
                minimum_free_bytes=0,
            ),
        )
    except SmokePreflightError as exc:
        assert "absent from the current frozen snapshot" in str(exc)
    else:
        raise AssertionError("missing fire event passed smoke preflight")
