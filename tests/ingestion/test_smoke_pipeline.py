from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from weather_ingest.cffeps import EmissionRow, apply_cumulative_area_curve
from weather_ingest.fbp_fuels import has_supported_cffeps_fuel, resolve_fbp_fuel
from weather_ingest.fire_events import Detection, EventMatchingConfig, reconcile_events
from weather_ingest.fire_scenarios import AreaMode, AreaPoint, FireWeatherCodes, SmokeScenarioConfig
from weather_ingest.flexpart_releases import compile_releases
from weather_ingest.flexpart_runner import derive_member_random_seed
from weather_ingest.simulation_jobs import emission_registry_warnings

START = datetime(2026, 7, 22, 6, tzinfo=UTC)


def _row(*, mass: float, layer: int = 0, species: str = "PM25") -> EmissionRow:
    return EmissionRow(
        run_id="test-run",
        event_id="event-a",
        source_time_start=START,
        source_time_end=START + timedelta(hours=1),
        latitude=45.0,
        longitude=-63.0,
        fuel_type="C2",
        combustion_phase="flaming",
        incremental_area_m2=1_000.0,
        fuel_consumption_kg_m2=2.0,
        species=species,
        emitted_mass_kg=mass,
        emission_rate_kg_s=mass / 3_600.0,
        plume_bottom_m_agl=float(layer * 100),
        plume_top_m_agl=float((layer + 1) * 100),
        vertical_layer_bottom_m_agl=float(layer * 100),
        vertical_layer_top_m_agl=float((layer + 1) * 100),
        vertical_fraction=0.25 if layer == 0 else 0.75,
        quality_flags="test",
    )


def _scenario(**overrides: object) -> SmokeScenarioConfig:
    values: dict[str, object] = {
        "name": "bounded test",
        "start_time": START,
        "end_time": START + timedelta(hours=1),
        "bbox": (-66.0, 43.0, -60.0, 48.0),
        "fire_weather": FireWeatherCodes(ffmc=90, dmc=40, dc=300),
    }
    values.update(overrides)
    return SmokeScenarioConfig.model_validate(values)


def test_fire_event_identity_is_independent_of_input_order() -> None:
    detections = [
        Detection(
            detection_id=f"detection-{index}",
            observed_at=START + timedelta(minutes=10 * index),
            latitude=45.0 + index * 0.002,
            longitude=-63.0,
            fuel="C2",
            properties={"detection_id": f"detection-{index}", "estarea": index + 1},
        )
        for index in range(6)
    ]
    config = EventMatchingConfig(
        algorithm_version="test-v1",
        maximum_time_gap_hours=24,
        maximum_distance_km=5,
        maximum_spread_km_per_hour=1,
        compatible_fuel_prefix_length=1,
        ambiguity_distance_ratio=1.2,
    )
    expected = reconcile_events(detections, config)
    random.Random(42).shuffle(detections)
    actual = reconcile_events(detections, config)
    assert actual["events"] == expected["events"]
    assert actual["event_count"] == 1
    memberships = [
        detection_id
        for event in actual["events"]
        for detection_id in event["member_detection_ids"]
    ]
    assert sorted(memberships) == [f"detection-{index}" for index in range(6)]


def test_fire_event_ambiguity_depends_only_on_two_nearest_candidates() -> None:
    detections = [
        Detection(
            detection_id=f"detection-{index}",
            observed_at=START + timedelta(minutes=index),
            latitude=45.0,
            longitude=-63.0,
            fuel="C2",
            properties={
                "detection_id": f"detection-{index}",
                "estarea": 1,
                "ffmc": 90,
                "dmc": 40,
                "dc": 300,
            },
        )
        for index in range(8)
    ]
    config = EventMatchingConfig(
        algorithm_version="test-v1",
        maximum_time_gap_hours=24,
        maximum_distance_km=5,
        maximum_spread_km_per_hour=1,
        compatible_fuel_prefix_length=1,
        ambiguity_distance_ratio=1.2,
    )

    result = reconcile_events(detections, config)

    assert result["event_count"] == 1
    assert result["events"][0]["warnings"]
    assert all(
        warning.startswith("ambiguous_match:")
        for warning in result["events"][0]["warnings"]
    )


def test_fire_event_reconciliation_retains_component_bridges() -> None:
    common = {"estarea": 1, "ffmc": 90, "dmc": 40, "dc": 300}
    detections = [
        Detection(
            detection_id="left",
            observed_at=START,
            latitude=45.0,
            longitude=-63.127,
            fuel="C2",
            properties={"detection_id": "left", **common},
        ),
        Detection(
            detection_id="right",
            observed_at=START,
            latitude=45.0,
            longitude=-62.873,
            fuel="C2",
            properties={"detection_id": "right", **common},
        ),
        Detection(
            detection_id="bridge",
            observed_at=START + timedelta(minutes=1),
            latitude=45.0,
            longitude=-63.0,
            fuel="C2",
            properties={"detection_id": "bridge", **common},
        ),
    ]
    config = EventMatchingConfig(
        algorithm_version="test-v1",
        maximum_time_gap_hours=24,
        maximum_distance_km=12,
        maximum_spread_km_per_hour=0,
        compatible_fuel_prefix_length=1,
        ambiguity_distance_ratio=1.2,
    )

    result = reconcile_events(detections, config)

    assert result["event_count"] == 1
    assert result["events"][0]["member_detection_ids"] == ["bridge", "left", "right"]


def test_custom_area_curve_scales_mass_and_preserves_consumption() -> None:
    rows = [_row(mass=1.0, layer=0), _row(mass=3.0, layer=1)]
    scaled, manifest = apply_cumulative_area_curve(
        rows,
        ((START, 1.0), (START + timedelta(hours=1), 1.2)),
    )
    assert sum(row.emitted_mass_kg for row in scaled) == pytest.approx(8.0)
    assert all(row.incremental_area_m2 == pytest.approx(2_000.0) for row in scaled)
    assert {row.fuel_consumption_kg_m2 for row in scaled} == {2.0}
    assert manifest["area_curve_algorithm"] == "linear_cumulative_area_v1"


def test_custom_area_curve_conserves_total_over_active_cffeps_intervals() -> None:
    row = replace(
        _row(mass=2.0),
        source_time_start=START + timedelta(hours=1),
        source_time_end=START + timedelta(hours=2),
    )

    scaled, manifest = apply_cumulative_area_curve(
        [row],
        ((START, 0.0), (START + timedelta(hours=2), 1.0)),
    )

    assert scaled[0].incremental_area_m2 == pytest.approx(10_000.0)
    assert scaled[0].emitted_mass_kg == pytest.approx(20.0)
    conservation = manifest["area_curve_active_interval_conservation"]
    assert conservation["initially_assigned_increment_m2"] == pytest.approx(5_000.0)
    assert conservation["normalization_factor"] == pytest.approx(2.0)
    assert conservation["final_assigned_increment_m2"] == pytest.approx(10_000.0)


def test_custom_area_curve_can_reproduce_legacy_unconserved_candidate() -> None:
    row = replace(
        _row(mass=2.0),
        source_time_start=START + timedelta(hours=1),
        source_time_end=START + timedelta(hours=2),
    )

    scaled, manifest = apply_cumulative_area_curve(
        [row],
        ((START, 0.0), (START + timedelta(hours=2), 1.0)),
        conserve_active_intervals=False,
    )

    assert scaled[0].incremental_area_m2 == pytest.approx(5_000.0)
    assert manifest["area_curve_active_interval_conservation"]["algorithm"] == (
        "disabled_for_legacy_candidate_reproduction"
    )


def test_custom_area_curve_must_cover_scenario_and_never_shrink() -> None:
    with pytest.raises(ValidationError, match="cover the full scenario"):
        _scenario(
            area_mode=AreaMode.USER_AREA_CURVE,
            event_ids=("event-a",),
            area_curve=(
                AreaPoint(time=START + timedelta(minutes=1), area_ha=1),
                AreaPoint(time=START + timedelta(hours=1), area_ha=2),
            ),
        )
    with pytest.raises(ValidationError, match="non-decreasing"):
        _scenario(
            area_mode=AreaMode.USER_AREA_CURVE,
            event_ids=("event-a",),
            area_curve=(
                AreaPoint(time=START, area_ha=2),
                AreaPoint(time=START + timedelta(hours=1), area_ha=1),
            ),
        )


def test_fixed_source_mode_is_not_silently_accepted() -> None:
    with pytest.raises(ValidationError, match="reserved for internal validation"):
        _scenario(area_mode=AreaMode.FIXED_SOURCE_TEST)


def test_release_compiler_conserves_each_species_and_particle_budget() -> None:
    rows = [
        _row(mass=1.25, layer=0, species="PM25"),
        _row(mass=3.75, layer=1, species="PM25"),
        _row(mass=10.0, layer=0, species="CO"),
        _row(mass=30.0, layer=1, species="CO"),
    ]
    releases, summary = compile_releases(
        rows,
        ("PM25", "CO"),
        particle_budget=10_000,
        minimum_particles=50,
    )
    assert summary["particle_count"] == 10_000
    assert summary["mass_kg_by_species"] == {"PM25": 5.0, "CO": 40.0}
    assert sum(release.mass_kg[0] for release in releases) == pytest.approx(5.0)
    assert sum(release.mass_kg[1] for release in releases) == pytest.approx(40.0)


def test_species_random_seeds_are_stable_distinct_and_bounded() -> None:
    seeds = {
        species: derive_member_random_seed(2_026_072_2, species)
        for species in ("PM25", "CO", "BC")
    }
    assert seeds == {"PM25": 20_261_623, "CO": 20_261_624, "BC": 20_261_625}
    assert derive_member_random_seed(2_147_483_647, "BC") == 903


def test_mixedwood_suffix_is_preserved_as_an_fbp_parameter() -> None:
    crosswalk = {"M1": "M1", "M2": "M2", "M3": "M3", "M4": "M4"}

    m2 = resolve_fbp_fuel("M2_25", crosswalk)
    m4 = resolve_fbp_fuel("M4_75", crosswalk)

    assert m2 is not None
    assert m2.model_code == "M2_25"
    assert m2.percent_conifer == 25
    assert m2.parameter_source == "cwfis_fuel_code_suffix"
    assert m4 is not None
    assert m4.model_code == "M4_75"
    assert m4.percent_dead_fir == 75


def test_model_eligible_fuel_filter_matches_cffeps_supported_bases() -> None:
    assert has_supported_cffeps_fuel(["C2"])
    assert has_supported_cffeps_fuel(["M2_25"])
    assert not has_supported_cffeps_fuel(["NF"])
    assert not has_supported_cffeps_fuel([])


def test_pending_registry_allows_warned_interactive_research_runs_only() -> None:
    pending = {
        "scientific_status": "validation_only",
        "review": {"status": "pending_independent_review"},
    }

    assert emission_registry_warnings("validation", pending) == []
    assert emission_registry_warnings("interactive", pending) == [
        "Research-only run: emission factors are pending independent scientific review"
    ]
    with pytest.raises(ValueError, match="independently approved"):
        emission_registry_warnings("operational", pending)

    approved = pending | {"review": {"status": "approved"}}
    assert emission_registry_warnings("operational", approved) == []


def test_legacy_explicit_fire_weather_is_a_manual_override() -> None:
    scenario = _scenario()

    assert scenario.fire_weather_mode.value == "manual"
    assert scenario.fire_weather == FireWeatherCodes(ffmc=90, dmc=40, dc=300)
