"""Strict CFFEPS 4.1 adapter and model-independent emissions bundle writer."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import netCDF4
import numpy as np
import yaml

from weather_ingest.gfs_profiles import AtmosphericProfile

FUEL_INDEX = {
    "C1": 1,
    "C2": 2,
    "C3": 3,
    "C4": 4,
    "C5": 5,
    "C6": 6,
    "C7": 7,
    "D1": 8,
    "D2": 8,
    "M1": 10,
    "M2": 11,
    "M3": 12,
    "M4": 13,
    "S1": 14,
    "S2": 15,
    "S3": 16,
    "O1A": 17,
    "O1B": 18,
}
PHASES = ("flaming", "smoldering", "residual")


@dataclass(frozen=True, slots=True)
class CffepsFire:
    event_id: str
    latitude: float
    longitude: float
    fuel_type: str
    estimated_area_ha: float
    detected_at: datetime
    ffmc: float
    dmc: float
    dc: float
    percent_conifer: float = 50.0
    percent_dead_fir: float = 35.0
    grass_curing_percent: float = 80.0

    def __post_init__(self) -> None:
        if self.detected_at.tzinfo is None:
            raise ValueError("fire detection time must be timezone-aware")
        if self.fuel_type.upper().split("_")[0] not in FUEL_INDEX:
            raise ValueError(f"unsupported CFFEPS fuel type {self.fuel_type}")
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("invalid fire coordinates")
        if not (0 < self.ffmc <= 101 and self.dmc > 0 and self.dc > 0):
            raise ValueError("CFFEPS requires positive FFMC, DMC, and DC")
        if self.estimated_area_ha <= 0:
            raise ValueError("estimated fire area must be positive")
        if any(
            not 0 <= value <= 100
            for value in (
                self.percent_conifer,
                self.percent_dead_fir,
                self.grass_curing_percent,
            )
        ):
            raise ValueError("FBP mixture and curing percentages must be in [0, 100]")


@dataclass(frozen=True, slots=True)
class EmissionRow:
    run_id: str
    event_id: str
    source_time_start: datetime
    source_time_end: datetime
    latitude: float
    longitude: float
    fuel_type: str
    combustion_phase: str
    incremental_area_m2: float
    fuel_consumption_kg_m2: float
    species: str
    emitted_mass_kg: float
    emission_rate_kg_s: float
    plume_bottom_m_agl: float
    plume_top_m_agl: float
    vertical_layer_bottom_m_agl: float
    vertical_layer_top_m_agl: float
    vertical_fraction: float
    quality_flags: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_emission_factors(
    path: Path, uncertainty: Literal["low", "central", "high"]
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2 or payload.get("fallback") != "reject":
        raise ValueError("unsupported emission-factor registry")
    if payload.get("units") != "g_species_per_kg_dry_fuel":
        raise ValueError("emission-factor registry has an unsupported mass basis")
    if payload.get("scientific_status") not in {"validation_only", "reviewed"}:
        raise ValueError("emission-factor registry has no valid scientific status")
    review = payload.get("review")
    if not isinstance(review, dict) or review.get("status") not in {
        "pending_independent_review",
        "approved",
    }:
        raise ValueError("emission-factor registry has no review state")
    factors: dict[str, dict[str, float]] = {}
    for species, definition in payload["species"].items():
        factors[species] = {
            phase: float(values[uncertainty]) for phase, values in definition["phases"].items()
        }
        if set(factors[species]) != set(PHASES) or any(
            value <= 0 for value in factors[species].values()
        ):
            raise ValueError(f"invalid emission factors for {species}")
        if not definition.get("citation") or not definition.get("doi"):
            raise ValueError(f"emission factors for {species} lack provenance")
    return factors, {
        "registry_version": payload["registry_version"],
        "registry_sha256": _sha256(path),
        "uncertainty": uncertainty,
        "scientific_status": payload["scientific_status"],
        "review_status": review["status"],
        "units": payload["units"],
    }


def _write_driver_inputs(
    work_dir: Path,
    fire: CffepsFire,
    profiles: list[AtmosphericProfile],
    fire_weather_states: list[tuple[float, float, float]] | None = None,
    estimated_area_states_ha: list[float] | None = None,
) -> tuple[Path, Path, Path, Path | None, Path | None]:
    if not profiles or len(profiles) > 24:
        raise ValueError("CFFEPS requires between one and 24 hourly profiles")
    expected = profiles[0].valid_time
    for profile in profiles:
        if profile.valid_time != expected:
            raise ValueError("CFFEPS profiles must be contiguous and hourly")
        if (
            abs(profile.latitude - fire.latitude) > 1e-6
            or abs(profile.longitude - fire.longitude) > 1e-6
        ):
            raise ValueError("profile location does not match fire location")
        expected = profile.valid_time + timedelta(hours=1)
    work_dir.mkdir(parents=True, exist_ok=False)
    profile_path = work_dir / "profiles.txt"
    output_path = work_dir / "cffeps-output.csv"
    config_path = work_dir / "cffeps.nml"
    fire_weather_state_path: Path | None = None
    estimated_area_state_path: Path | None = None
    lines: list[str] = []
    for profile in profiles:
        time = profile.valid_time.astimezone(UTC)
        lines.append(
            f"{time.year} {time.month} {time.day} {time.hour} "
            f"{profile.specific_humidity_kg_kg:.9g} {profile.wind_speed_knots:.9g} "
            f"{profile.dewpoint_k:.9g}"
        )
        for pressure, temperature, height in zip(
            profile.pressure_pa, profile.temperature_k, profile.height_m_agl, strict=True
        ):
            lines.append(f"{pressure:.9g} {temperature:.9g} {height:.9g}")
    profile_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    if fire_weather_states is not None:
        if len(fire_weather_states) != len(profiles):
            raise ValueError("CFFEPS requires one fire-weather state per hourly profile")
        if any(
            not (0.0 < ffmc <= 101.0 and dmc > 0.0 and dc > 0.0)
            for ffmc, dmc, dc in fire_weather_states
        ):
            raise ValueError("CFFEPS fire-weather state profile is invalid")
        fire_weather_state_path = work_dir / "fire-weather-states.txt"
        fire_weather_state_path.write_text(
            "".join(f"{ffmc:.9g} {dmc:.9g} {dc:.9g}\n" for ffmc, dmc, dc in fire_weather_states),
            encoding="ascii",
        )
    if estimated_area_states_ha is not None:
        if len(estimated_area_states_ha) != len(profiles):
            raise ValueError("CFFEPS requires one cumulative estimated area per hourly profile")
        if any(value < 0.0 for value in estimated_area_states_ha):
            raise ValueError("CFFEPS hourly estimated areas must be nonnegative")
        if any(
            later < earlier
            for earlier, later in zip(
                estimated_area_states_ha,
                estimated_area_states_ha[1:],
                strict=False,
            )
        ):
            raise ValueError("CFFEPS hourly estimated areas must be non-decreasing")
        estimated_area_state_path = work_dir / "estimated-area-states.txt"
        estimated_area_state_path.write_text(
            "".join(f"{value:.9g}\n" for value in estimated_area_states_ha),
            encoding="ascii",
        )
    detected = fire.detected_at.astimezone(UTC)
    julian = int(detected.strftime("%j"))
    fuel = fire.fuel_type.upper().split("_")[0]
    nml = (
        "&portable_cffeps\n"
        f" profile_path='{profile_path.as_posix()}'\n"
        f" output_path='{output_path.as_posix()}'\n"
        f" fueltype_index={FUEL_INDEX[fuel]}\n"
        f" detection_julian={julian}\n"
        f" detection_hhmm={detected.hour * 100 + detected.minute}\n"
        f" nsteps={len(profiles)}\n"
        f" lat={fire.latitude:.8f}\n lon={fire.longitude:.8f}\n"
        f" ffmc={fire.ffmc:.6f}\n dmc={fire.dmc:.6f}\n dc={fire.dc:.6f}\n"
        f" percent_conifer={fire.percent_conifer:.6f}\n"
        f" percent_dead_fir={fire.percent_dead_fir:.6f}\n"
        f" grass_curing_percent={fire.grass_curing_percent:.6f}\n"
        f" estarea_ha={fire.estimated_area_ha:.6f}\n"
        f" elevation_m={profiles[0].elevation_m:.6f}\n"
        + (
            f" fire_weather_state_path='{fire_weather_state_path.as_posix()}'\n"
            if fire_weather_state_path is not None
            else ""
        )
        + (
            f" estimated_area_state_path='{estimated_area_state_path.as_posix()}'\n"
            if estimated_area_state_path is not None
            else ""
        )
        + " cffeps_fire_shape='weighted'\n cffeps_fire_type='dry'\n/\n"
    )
    config_path.write_text(nml, encoding="ascii")
    return (
        config_path,
        profile_path,
        output_path,
        fire_weather_state_path,
        estimated_area_state_path,
    )


def _vertical_layers(
    plume_top: float,
    phase: str,
    count: int,
    algorithm: str = "cffeps_top_beta_v1",
) -> list[tuple[float, float, float]]:
    if plume_top <= 0:
        return [(0.0, 10.0, 1.0)]
    if algorithm == "uniform_surface_to_cffeps_top_v1":
        edges = np.linspace(0.0, max(plume_top, 10.0), count + 1)
        return [
            (
                float(edges[index]),
                float(edges[index + 1]),
                1.0 / count,
            )
            for index in range(count)
        ]
    if algorithm != "cffeps_top_beta_v1":
        raise ValueError("unsupported CFFEPS vertical-profile algorithm")
    phase_bounds = {
        "flaming": (0.25, 1.0, 3.0),
        "smoldering": (0.05, 0.65, 1.5),
        "residual": (0.0, 0.35, 0.8),
    }
    lower_fraction, upper_fraction, shape = phase_bounds[phase]
    lower = lower_fraction * plume_top
    upper = max(upper_fraction * plume_top, lower + 10.0)
    edges = np.linspace(lower, upper, count + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    scaled = np.clip((centers - lower) / max(upper - lower, 1.0), 0.0, 1.0)
    weights = np.maximum(scaled**shape, 1e-12)
    weights /= weights.sum()
    return [
        (float(edges[index]), float(edges[index + 1]), float(weights[index]))
        for index in range(count)
    ]


def run_cffeps(
    *,
    run_id: str,
    fire: CffepsFire,
    profiles: list[AtmosphericProfile],
    executable: Path,
    work_dir: Path,
    emission_factors_path: Path,
    species: tuple[str, ...] = ("PM25", "CO", "BC"),
    uncertainty: Literal["low", "central", "high"] = "central",
    vertical_layer_count: int = 12,
    vertical_profile_algorithm: str = "cffeps_top_beta_v1",
    fire_weather_states: list[tuple[float, float, float]] | None = None,
    estimated_area_states_ha: list[float] | None = None,
    timeout_seconds: int = 300,
) -> tuple[list[EmissionRow], dict[str, Any]]:
    executable = executable.resolve()
    work_dir = work_dir.resolve()
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("CFFEPS executable is missing or unsafe")
    if not 1 <= vertical_layer_count <= 20:
        raise ValueError("vertical layer count must be in [1, 20]")
    factors, factor_provenance = load_emission_factors(emission_factors_path, uncertainty)
    if set(species) - factors.keys():
        raise ValueError("requested species is absent from the emission-factor registry")
    (
        config_path,
        profile_path,
        output_path,
        fire_weather_state_path,
        estimated_area_state_path,
    ) = _write_driver_inputs(
        work_dir,
        fire,
        profiles,
        fire_weather_states,
        estimated_area_states_ha,
    )
    process = subprocess.run(
        [str(executable), str(config_path)],
        cwd=work_dir.parent,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env={"PATH": os.environ.get("PATH", "")},
    )
    (work_dir / "stdout.log").write_text(process.stdout, encoding="utf-8")
    (work_dir / "stderr.log").write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0 or not output_path.is_file():
        raise RuntimeError(
            f"CFFEPS failed with exit code {process.returncode}: {process.stderr[-1000:]}"
        )

    rows: list[EmissionRow] = []
    previous_area_ha = 0.0
    phase_fuel_tonnes_sum = 0.0
    reported_total_consumed_fuel_tonnes = 0.0
    final_pending_fuel_tonnes = {
        "flaming": 0.0,
        "smoldering": 0.0,
        "residual": 0.0,
    }
    phase_columns = {
        "flaming": "flaming_fuel_t_h",
        "smoldering": "smoldering_fuel_t_h",
        "residual": "residual_fuel_t_h",
    }
    pending_columns = {
        "flaming": "pending_flaming_fuel_t",
        "smoldering": "pending_smoldering_fuel_t",
        "residual": "pending_residual_fuel_t",
    }
    with output_path.open(newline="", encoding="ascii") as source:
        for output in csv.DictReader(source):
            index = int(output["step"])
            start = profiles[index].valid_time.astimezone(UTC)
            end = start + timedelta(hours=1)
            area_ha = float(output["fire_area_ha"])
            incremental_area_m2 = max(area_ha - previous_area_ha, 0.0) * 10_000.0
            previous_area_ha = max(previous_area_ha, area_ha)
            plume_top = max(float(output["plume_top_m_agl"]), 0.0)
            reported_total_consumed_fuel_tonnes = max(float(output["total_consumed_fuel_t"]), 0.0)
            for phase, column in pending_columns.items():
                if column not in output:
                    raise ValueError("CFFEPS portable output lacks finite-window phase queues")
                final_pending_fuel_tonnes[phase] = max(float(output[column]), 0.0)
            for phase, column in phase_columns.items():
                fuel_tonnes = max(float(output[column]), 0.0)
                phase_fuel_tonnes_sum += fuel_tonnes
                if fuel_tonnes == 0:
                    continue
                phase_layers = _vertical_layers(
                    plume_top,
                    phase,
                    vertical_layer_count,
                    vertical_profile_algorithm,
                )
                fuel_consumption = (
                    fuel_tonnes * 1000.0 / incremental_area_m2 if incremental_area_m2 else 0.0
                )
                for specie in species:
                    species_mass_kg = fuel_tonnes * factors[specie][phase]
                    for layer_bottom, layer_top, fraction in phase_layers:
                        mass = species_mass_kg * fraction
                        rows.append(
                            EmissionRow(
                                run_id=run_id,
                                event_id=fire.event_id,
                                source_time_start=start,
                                source_time_end=end,
                                latitude=fire.latitude,
                                longitude=fire.longitude,
                                fuel_type=fire.fuel_type,
                                combustion_phase=phase,
                                incremental_area_m2=incremental_area_m2,
                                fuel_consumption_kg_m2=fuel_consumption,
                                species=specie,
                                emitted_mass_kg=mass,
                                emission_rate_kg_s=mass / 3600.0,
                                plume_bottom_m_agl=phase_layers[0][0],
                                plume_top_m_agl=phase_layers[-1][1],
                                vertical_layer_bottom_m_agl=layer_bottom,
                                vertical_layer_top_m_agl=layer_top,
                                vertical_fraction=fraction,
                                quality_flags=(
                                    f"cffeps_4_1;vertical_profile:{vertical_profile_algorithm}"
                                ),
                            )
                        )
    pending_fuel_tonnes_sum = sum(final_pending_fuel_tonnes.values())
    closed_fuel_tonnes_sum = phase_fuel_tonnes_sum + pending_fuel_tonnes_sum
    fuel_mass_relative_difference = (
        abs(closed_fuel_tonnes_sum - reported_total_consumed_fuel_tonnes)
        / reported_total_consumed_fuel_tonnes
        if reported_total_consumed_fuel_tonnes > 0
        else 0.0
    )
    maximum_mass_relative_difference = 0.05
    at_numerical_tolerance_of_limit = math.isclose(
        fuel_mass_relative_difference,
        maximum_mass_relative_difference,
        rel_tol=1e-5,
        abs_tol=1e-8,
    )
    if (
        fuel_mass_relative_difference > maximum_mass_relative_difference
        and not at_numerical_tolerance_of_limit
    ):
        raise ValueError(
            "CFFEPS released-plus-pending phase fuel does not agree with its "
            "cumulative consumed-fuel total"
        )
    pending_fraction = (
        pending_fuel_tonnes_sum / reported_total_consumed_fuel_tonnes
        if reported_total_consumed_fuel_tonnes > 0
        else 0.0
    )
    released_fraction = (
        phase_fuel_tonnes_sum / reported_total_consumed_fuel_tonnes
        if reported_total_consumed_fuel_tonnes > 0
        else 0.0
    )
    accounted_fraction = (
        closed_fuel_tonnes_sum / reported_total_consumed_fuel_tonnes
        if reported_total_consumed_fuel_tonnes > 0
        else 0.0
    )
    mass_by_species = {
        specie: sum(row.emitted_mass_kg for row in rows if row.species == specie)
        for specie in species
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "event_id": fire.event_id,
        "model": "CFFEPS",
        "model_version": "4.1",
        "executable_sha256": _sha256(executable),
        "driver_config_sha256": _sha256(config_path),
        "profiles_sha256": _sha256(profile_path),
        "fire_weather_states": (
            {
                "operator": ("latest_causal_firem3_state_at_or_before_profile_hour_v1"),
                "sha256": _sha256(fire_weather_state_path),
                "hour_count": len(fire_weather_states),
            }
            if fire_weather_state_path is not None and fire_weather_states is not None
            else {
                "operator": "constant_cffeps_fire_state",
                "sha256": None,
                "hour_count": len(profiles),
            }
        ),
        "estimated_area_states": (
            {
                "operator": "causal_cumulative_area_through_profile_hour_v1",
                "sha256": _sha256(estimated_area_state_path),
                "hour_count": len(estimated_area_states_ha),
            }
            if estimated_area_state_path is not None and estimated_area_states_ha is not None
            else {
                "operator": "constant_cffeps_estimated_area",
                "sha256": None,
                "hour_count": len(profiles),
            }
        ),
        "raw_output_sha256": _sha256(output_path),
        "factor_registry": factor_provenance,
        "fbp_fuel_parameters": {
            "fuel_type": fire.fuel_type,
            "percent_conifer": fire.percent_conifer,
            "percent_dead_fir": fire.percent_dead_fir,
            "grass_curing_percent": fire.grass_curing_percent,
        },
        "vertical_profile_algorithm": vertical_profile_algorithm,
        "row_count": len(rows),
        "mass_kg_by_species": mass_by_species,
        "fuel_mass_balance": {
            "accounting": "released_plus_pending_queue_equals_cumulative_consumption_v1",
            "released_within_window_phase_fuel_tonnes": phase_fuel_tonnes_sum,
            "final_pending_phase_fuel_tonnes": final_pending_fuel_tonnes,
            "final_pending_phase_fuel_tonnes_sum": pending_fuel_tonnes_sum,
            "closed_phase_fuel_tonnes_sum": closed_fuel_tonnes_sum,
            "reported_cumulative_consumed_fuel_tonnes": (reported_total_consumed_fuel_tonnes),
            "relative_difference": fuel_mass_relative_difference,
            "maximum_relative_difference": maximum_mass_relative_difference,
            "passed": True,
            "released_within_window_fraction": released_fraction,
            "pending_after_window_fraction": pending_fraction,
            "released_plus_pending_accounted_fraction": accounted_fraction,
            "unaccounted_fraction": max(1.0 - accounted_fraction, 0.0),
        },
        "warnings": [
            "CFFEPS 4.1 reports plume top; normalized layer fractions use "
            "the versioned fallback profile",
            "CFFEPS phase fuel still pending after the finite driver window is "
            "reported but is outside this transport member",
        ],
    }
    return rows, manifest


def apply_cumulative_area_curve(
    rows: list[EmissionRow],
    curve: tuple[tuple[datetime, float], ...],
    *,
    conserve_active_intervals: bool = True,
) -> tuple[list[EmissionRow], dict[str, Any]]:
    """Scale hourly CFFEPS output to a cumulative burned-area curve."""
    if len(curve) < 2:
        raise ValueError("area curve requires at least two points")
    if any(time.tzinfo is None for time, _ in curve):
        raise ValueError("area curve times must be timezone-aware")
    normalized = tuple((time.astimezone(UTC), float(area)) for time, area in curve)
    if any(
        later_time <= earlier_time or later_area < earlier_area
        for (earlier_time, earlier_area), (later_time, later_area) in zip(
            normalized, normalized[1:], strict=False
        )
    ):
        raise ValueError("area curve must be strictly ordered and non-decreasing")

    def interpolate(target: datetime) -> float:
        target = target.astimezone(UTC)
        if target < normalized[0][0] or target > normalized[-1][0]:
            raise ValueError("area curve does not cover CFFEPS output interval")
        for (left_time, left_area), (right_time, right_area) in zip(
            normalized, normalized[1:], strict=False
        ):
            if left_time <= target <= right_time:
                width = (right_time - left_time).total_seconds()
                fraction = (target - left_time).total_seconds() / width
                return left_area + fraction * (right_area - left_area)
        return normalized[-1][1]

    increments: dict[tuple[datetime, datetime], float] = {}
    native_increments: dict[tuple[datetime, datetime], float] = {}
    for row in rows:
        key = (row.source_time_start, row.source_time_end)
        increments[key] = (
            interpolate(row.source_time_end) - interpolate(row.source_time_start)
        ) * 10_000.0
        native_increments[key] = max(native_increments.get(key, 0.0), row.incremental_area_m2)

    requested_total_increment = (normalized[-1][1] - normalized[0][1]) * 10_000.0
    initially_assigned_increment = sum(increments.values())
    if requested_total_increment > 0 and initially_assigned_increment <= 0:
        raise ValueError("area curve has positive growth but no active CFFEPS intervals")
    conservation_factor = (
        requested_total_increment / initially_assigned_increment
        if initially_assigned_increment > 0
        else 1.0
    )
    active_interval_normalization = conservation_factor if conserve_active_intervals else 1.0
    increments = {
        key: increment * active_interval_normalization for key, increment in increments.items()
    }

    scaled: list[EmissionRow] = []
    for row in rows:
        key = (row.source_time_start, row.source_time_end)
        desired_increment = increments[key]
        native_increment = native_increments[key]
        if desired_increment > 0 and native_increment <= 0:
            raise ValueError("CFFEPS produced no fuel consumption for a positive area increment")
        factor = desired_increment / native_increment if native_increment > 0 else 0.0
        scaled.append(
            replace(
                row,
                incremental_area_m2=desired_increment,
                emitted_mass_kg=row.emitted_mass_kg * factor,
                emission_rate_kg_s=row.emission_rate_kg_s * factor,
                quality_flags=f"{row.quality_flags};area_mode:user_area_curve_v1",
            )
        )
    return scaled, {
        "area_mode": "user_area_curve",
        "area_curve_algorithm": "linear_cumulative_area_v1",
        "area_curve_active_interval_conservation": {
            "algorithm": (
                "proportional_normalization_over_active_cffeps_intervals_v1"
                if conserve_active_intervals
                else "disabled_for_legacy_candidate_reproduction"
            ),
            "active_interval_count": len(increments),
            "requested_total_increment_m2": requested_total_increment,
            "initially_assigned_increment_m2": initially_assigned_increment,
            "normalization_factor": active_interval_normalization,
            "final_assigned_increment_m2": sum(increments.values()),
        },
        "area_curve": [
            {"time": time.isoformat().replace("+00:00", "Z"), "area_ha": area}
            for time, area in normalized
        ],
        "incremental_area_m2": {
            start.isoformat().replace("+00:00", "Z"): increment
            for (start, _), increment in sorted(increments.items())
        },
    }


def write_emission_bundle(
    path: Path, rows: list[EmissionRow], manifest: dict[str, Any]
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with netCDF4.Dataset(temporary, "w", format="NETCDF4") as dataset:
        dataset.createDimension("row", len(rows))
        dataset.schema_version = 1
        dataset.title = "Normalized wildfire emissions and vertical injection bundle"
        dataset.manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        string_fields = (
            "run_id",
            "event_id",
            "fuel_type",
            "combustion_phase",
            "species",
            "quality_flags",
        )
        for field in string_fields:
            variable = dataset.createVariable(field, str, ("row",))
            variable[:] = np.array([getattr(row, field) for row in rows], dtype=object)
        time_units = "seconds since 1970-01-01 00:00:00 UTC"
        for field in ("source_time_start", "source_time_end"):
            variable = dataset.createVariable(field, "i8", ("row",), zlib=True)
            variable.units = time_units
            variable[:] = [int(getattr(row, field).timestamp()) for row in rows]
        numeric_fields = (
            "latitude",
            "longitude",
            "incremental_area_m2",
            "fuel_consumption_kg_m2",
            "emitted_mass_kg",
            "emission_rate_kg_s",
            "plume_bottom_m_agl",
            "plume_top_m_agl",
            "vertical_layer_bottom_m_agl",
            "vertical_layer_top_m_agl",
            "vertical_fraction",
        )
        for field in numeric_fields:
            variable = dataset.createVariable(field, "f8", ("row",), zlib=True)
            variable[:] = [getattr(row, field) for row in rows]
    temporary.replace(path)
    manifest_path = path.with_suffix(".manifest.json")
    final = manifest | {
        "bundle": {
            "filename": path.name,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
    }
    manifest_path.write_text(
        json.dumps(final, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return final


def validate_emission_bundle(path: Path, *, relative_tolerance: float = 1e-10) -> dict[str, float]:
    with netCDF4.Dataset(path) as dataset:
        mass = np.asarray(dataset.variables["emitted_mass_kg"][:], dtype=float)
        fractions = np.asarray(dataset.variables["vertical_fraction"][:], dtype=float)
        if not np.all(np.isfinite(mass)) or np.any(mass < 0):
            raise ValueError("emission bundle has invalid mass")
        if not np.all(np.isfinite(fractions)) or np.any(fractions <= 0) or np.any(fractions > 1):
            raise ValueError("emission bundle has invalid vertical fractions")
        starts = np.asarray(dataset.variables["source_time_start"][:])
        events = np.asarray(dataset.variables["event_id"][:]).astype(str)
        phases = np.asarray(dataset.variables["combustion_phase"][:]).astype(str)
        species = np.asarray(dataset.variables["species"][:]).astype(str)
        for key in set(zip(events, starts, phases, species, strict=True)):
            mask = (
                (events == key[0]) & (starts == key[1]) & (phases == key[2]) & (species == key[3])
            )
            total = float(fractions[mask].sum())
            if not math.isclose(total, 1.0, rel_tol=relative_tolerance, abs_tol=relative_tolerance):
                raise ValueError(f"vertical fractions do not sum to one for {key}: {total}")
        return {"row_count": float(len(mass)), "total_mass_kg": float(mass.sum())}


def read_emission_bundle(path: Path) -> list[EmissionRow]:
    """Load a validated normalized bundle for the FLEXPART release compiler."""

    validate_emission_bundle(path)
    with netCDF4.Dataset(path) as dataset:
        row_count = len(dataset.dimensions["row"])
        strings = {
            name: np.asarray(dataset.variables[name][:]).astype(str)
            for name in (
                "run_id",
                "event_id",
                "fuel_type",
                "combustion_phase",
                "species",
                "quality_flags",
            )
        }
        numbers = {
            name: np.asarray(dataset.variables[name][:], dtype=float)
            for name in (
                "latitude",
                "longitude",
                "incremental_area_m2",
                "fuel_consumption_kg_m2",
                "emitted_mass_kg",
                "emission_rate_kg_s",
                "plume_bottom_m_agl",
                "plume_top_m_agl",
                "vertical_layer_bottom_m_agl",
                "vertical_layer_top_m_agl",
                "vertical_fraction",
            )
        }
        starts = np.asarray(dataset.variables["source_time_start"][:], dtype=np.int64)
        ends = np.asarray(dataset.variables["source_time_end"][:], dtype=np.int64)
        return [
            EmissionRow(
                run_id=strings["run_id"][index],
                event_id=strings["event_id"][index],
                source_time_start=datetime.fromtimestamp(int(starts[index]), UTC),
                source_time_end=datetime.fromtimestamp(int(ends[index]), UTC),
                latitude=float(numbers["latitude"][index]),
                longitude=float(numbers["longitude"][index]),
                fuel_type=strings["fuel_type"][index],
                combustion_phase=strings["combustion_phase"][index],
                incremental_area_m2=float(numbers["incremental_area_m2"][index]),
                fuel_consumption_kg_m2=float(numbers["fuel_consumption_kg_m2"][index]),
                species=strings["species"][index],
                emitted_mass_kg=float(numbers["emitted_mass_kg"][index]),
                emission_rate_kg_s=float(numbers["emission_rate_kg_s"][index]),
                plume_bottom_m_agl=float(numbers["plume_bottom_m_agl"][index]),
                plume_top_m_agl=float(numbers["plume_top_m_agl"][index]),
                vertical_layer_bottom_m_agl=float(numbers["vertical_layer_bottom_m_agl"][index]),
                vertical_layer_top_m_agl=float(numbers["vertical_layer_top_m_agl"][index]),
                vertical_fraction=float(numbers["vertical_fraction"][index]),
                quality_flags=strings["quality_flags"][index],
            )
            for index in range(row_count)
        ]
