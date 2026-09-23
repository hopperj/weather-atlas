from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weather_ingest.cffeps import _vertical_layers
from weather_ingest.flexpart_config import (
    FlexpartDeposition,
    FlexpartDomain,
    parse_namelist_scalars,
    write_command,
)
from weather_ingest.smoke_validation_candidate import (
    CandidateConfig,
    dominant_event_fuel,
    run_validation_candidate,
)


def test_dominant_event_fuel_uses_unique_modal_frozen_detection_code() -> None:
    event = {
        "event_id": "event-1",
        "detections": [
            {"model_fuel": "C2"},
            {"model_fuel": "C3"},
            {"model_fuel": "C3"},
        ],
    }

    fuel, counts = dominant_event_fuel(event, {"C2": "C2", "C3": "C3"})

    assert fuel.model_code == "C3"
    assert counts == {"C2": 1, "C3": 2}


def test_dominant_event_fuel_rejects_tie() -> None:
    event = {
        "event_id": "event-1",
        "detections": [{"model_fuel": "C2"}, {"model_fuel": "C3"}],
    }

    with pytest.raises(ValueError, match="tied dominant fuels"):
        dominant_event_fuel(event, {"C2": "C2", "C3": "C3"})


@pytest.mark.parametrize("workers", [0, 9])
def test_validation_candidate_rejects_unsafe_transport_worker_count(workers: int) -> None:
    with pytest.raises(ValueError, match="transport_workers"):
        run_validation_candidate(
            data_root=None,  # type: ignore[arg-type]
            event_area_path=None,  # type: ignore[arg-type]
            events_path=None,  # type: ignore[arg-type]
            candidate_config_path=None,  # type: ignore[arg-type]
            crosswalk_path=None,  # type: ignore[arg-type]
            emission_factors_path=None,  # type: ignore[arg-type]
            cffeps_executable=None,  # type: ignore[arg-type]
            flexpart_root=None,  # type: ignore[arg-type]
            flexpart_executable=None,  # type: ignore[arg-type]
            output_directory=None,  # type: ignore[arg-type]
            transport_workers=workers,
        )


def test_flexpart_domain_accepts_frozen_canada_wide_grid() -> None:
    domain = FlexpartDomain(
        west=-141,
        south=41,
        east=-52,
        north=84,
        spacing=1.0,
    )

    assert domain.nx == 90
    assert domain.ny == 44


def test_flexpart_domain_rejects_more_than_fifty_thousand_cells() -> None:
    with pytest.raises(ValueError, match="configured bound"):
        FlexpartDomain(
            west=-180,
            south=-90,
            east=180,
            north=90,
            spacing=0.25,
        )


def test_uniform_vertical_sensitivity_conserves_mass_from_surface_to_top() -> None:
    layers = _vertical_layers(
        1200.0,
        "flaming",
        12,
        "uniform_surface_to_cffeps_top_v1",
    )

    assert layers[0][0] == 0.0
    assert layers[-1][1] == 1200.0
    assert sum(layer[2] for layer in layers) == pytest.approx(1.0)
    assert all(layer[2] == pytest.approx(1.0 / 12.0) for layer in layers)


def test_derived_sensitivity_config_deep_merges_frozen_base() -> None:
    config = CandidateConfig.from_yaml(
        Path("config/smoke/validation_candidate_2026_sensitivity_ef_low_v6.yaml")
    )

    assert config.candidate_version == "march-may-2026-mcd64a1-ef-low-v6"
    assert config.emission_factor_uncertainty == "low"
    assert config.particle_budget_per_species_day == 150_000
    assert len(config.source_paths) == 2


def test_successor_candidate_freezes_all_deposition_switches() -> None:
    config = CandidateConfig.from_yaml(
        Path("config/smoke/validation_candidate_successor_2023_v1.yaml")
    )

    assert config.deposition == FlexpartDeposition(
        wet=True,
        dry=True,
        settling=True,
    )


def test_flexpart_command_can_disable_dry_deposition_while_retaining_settling(
    tmp_path: Path,
) -> None:
    start = datetime(2023, 6, 1, tzinfo=UTC)
    deposition = FlexpartDeposition(wet=True, dry=False, settling=True)
    path = tmp_path / "COMMAND"

    write_command(
        path,
        start,
        start + timedelta(days=1),
        threads=8,
        deposition=deposition,
    )

    values = parse_namelist_scalars(path)
    assert values["WETDEP_ENABLED"] == ".true."
    assert values["DRYDEP_ENABLED"] == ".false."
    assert deposition.settling


def test_flexpart_deposition_sensitivity_cannot_disable_settling() -> None:
    with pytest.raises(ValueError, match="settling"):
        FlexpartDeposition(wet=True, dry=True, settling=False)
