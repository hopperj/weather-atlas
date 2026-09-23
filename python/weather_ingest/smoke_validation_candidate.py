"""Standalone, publication-oriented CFFEPS/FLEXPART validation candidate runner."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

import yaml

from weather_ingest.cffeps import (
    CffepsFire,
    EmissionRow,
    apply_cumulative_area_curve,
    run_cffeps,
    validate_emission_bundle,
    write_emission_bundle,
)
from weather_ingest.cwfis_cffdrs import sample_fire_weather
from weather_ingest.fbp_fuels import FbpFuel, resolve_fbp_fuel
from weather_ingest.flexpart_config import FlexpartDeposition, FlexpartDomain
from weather_ingest.flexpart_runner import (
    FlexpartRunLimits,
    derive_member_random_seed,
    prepare_species_runs,
    run_flexpart,
)
from weather_ingest.gfs_profiles import extract_cycle_profiles


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    source_paths: tuple[Path, ...]
    candidate_version: str
    area_operator_version: str
    require_complete_fire_weather: bool
    nominal_detection_hour_utc: int
    daily_area_allocation: str
    phase_tail_policy: str
    mass_balance_accounting: str
    species: tuple[str, ...]
    emission_factor_uncertainty: str
    vertical_layer_count: int
    vertical_profile_algorithm: str
    area_curve: str
    domain: FlexpartDomain
    deposition: FlexpartDeposition
    particle_budget_per_species_day: int
    minimum_particles_per_release: int
    maximum_releases: int
    threads: int
    base_random_seed: int

    @classmethod
    def from_yaml(cls, path: Path) -> CandidateConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported smoke validation candidate configuration")
        source_paths = (path,)
        if "base_config" in payload:
            base_path = (path.parent / str(payload["base_config"])).resolve()
            base_payload = yaml.safe_load(base_path.read_text(encoding="utf-8"))
            if (
                not isinstance(base_payload, dict)
                or base_payload.get("schema_version") != 1
            ):
                raise ValueError("unsupported base candidate configuration")
            overrides = payload.get("overrides")
            if not isinstance(overrides, dict):
                raise ValueError("derived candidate configuration requires overrides")

            def merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
                result = dict(base)
                for key, value in changes.items():
                    if isinstance(value, dict) and isinstance(result.get(key), dict):
                        result[key] = merge(result[key], value)
                    else:
                        result[key] = value
                return result

            payload = merge(base_payload, overrides)
            source_paths = (path, base_path)
        selection_rule = str(payload["selection"]["rule"])
        supported_selection_rules = {
            "all_burned_area_eligible_events",
            "all_burned_area_eligible_events_with_complete_required_inputs",
        }
        if selection_rule not in supported_selection_rules:
            raise ValueError("unsupported candidate event-selection rule")
        if payload["selection"]["require_unique_dominant_detection_fuel"] is not True:
            raise ValueError("validation candidate requires a unique dominant fuel")
        require_complete_fire_weather = bool(
            payload["selection"].get(
                "require_complete_fire_weather_for_every_source_day",
                False,
            )
        )
        if (
            selection_rule
            == "all_burned_area_eligible_events_with_complete_required_inputs"
            and not require_complete_fire_weather
        ):
            raise ValueError("complete-input selection requires complete fire weather")
        daily_area_allocation = str(payload["source_time"]["daily_area_allocation"])
        if daily_area_allocation not in {
            "linear_utc_00_to_24",
            "linear_utc_daily_total_conserved_over_active_cffeps_intervals_v1",
        }:
            raise ValueError("unsupported daily area allocation")
        if payload["fire_weather"]["sampling"] != "nearest_grid_cell_v1":
            raise ValueError("unsupported CWFIS sampling")
        phase_tail_policy = str(
            payload["source_time"].get(
                "phase_tail_policy",
                "unreported_legacy_24_hour_window",
            )
        )
        mass_balance_accounting = str(
            payload["source_time"].get(
                "mass_balance_accounting",
                "released_only_legacy_accounting",
            )
        )
        supported_tail_policies = {
            "unreported_legacy_24_hour_window",
            "retain_only_phase_mass_released_within_24_hour_transport_window_v1",
        }
        supported_balance_accounting = {
            "released_only_legacy_accounting",
            "released_plus_pending_queue_equals_cumulative_consumption_v1",
        }
        if phase_tail_policy not in supported_tail_policies:
            raise ValueError("unsupported CFFEPS phase-tail policy")
        if mass_balance_accounting not in supported_balance_accounting:
            raise ValueError("unsupported CFFEPS mass-balance accounting")
        if phase_tail_policy.endswith("_v1") != mass_balance_accounting.endswith("_v1"):
            raise ValueError("CFFEPS phase-tail and mass-balance policies must be paired")
        emission_factor_uncertainty = str(
            payload["cffeps"]["emission_factor_uncertainty"]
        )
        if emission_factor_uncertainty not in {"low", "central", "high"}:
            raise ValueError("unsupported emission-factor uncertainty selection")
        vertical_profile_algorithm = str(
            payload["cffeps"].get(
                "vertical_profile_algorithm",
                "cffeps_top_beta_v1",
            )
        )
        if vertical_profile_algorithm not in {
            "cffeps_top_beta_v1",
            "uniform_surface_to_cffeps_top_v1",
        }:
            raise ValueError("unsupported vertical-profile algorithm")
        area_curve = str(
            payload["selection"].get("area_curve", "central_daily_increment_ha")
        )
        if area_curve not in {
            "central_daily_increment_ha",
            "high_confidence_daily_increment_ha",
            "independent_low_daily_increment_ha",
            "independent_high_daily_increment_ha",
            "earliest_timing_daily_increment_ha",
            "latest_timing_daily_increment_ha",
        }:
            raise ValueError("unsupported burned-area sensitivity curve")
        if payload["flexpart"]["species_members"] != "isolated":
            raise ValueError("FLEXPART validation species must remain isolated")
        deposition = payload["flexpart"].get(
            "deposition",
            {"wet": True, "dry": True, "settling": True},
        )
        if not isinstance(deposition, dict) or any(
            not isinstance(deposition.get(name), bool)
            for name in ("wet", "dry", "settling")
        ):
            raise ValueError("FLEXPART deposition switches must be explicit booleans")
        domain = payload["flexpart"]["domain_wgs84"]
        return cls(
            source_paths=source_paths,
            candidate_version=str(payload["candidate_version"]),
            area_operator_version=str(payload["area_operator_version"]),
            require_complete_fire_weather=require_complete_fire_weather,
            nominal_detection_hour_utc=int(
                payload["source_time"]["nominal_detection_hour_utc"]
            ),
            daily_area_allocation=daily_area_allocation,
            phase_tail_policy=phase_tail_policy,
            mass_balance_accounting=mass_balance_accounting,
            species=tuple(str(value) for value in payload["cffeps"]["species"]),
            emission_factor_uncertainty=emission_factor_uncertainty,
            vertical_layer_count=int(payload["cffeps"]["vertical_layer_count"]),
            vertical_profile_algorithm=vertical_profile_algorithm,
            area_curve=area_curve,
            domain=FlexpartDomain(
                west=float(domain["west"]),
                south=float(domain["south"]),
                east=float(domain["east"]),
                north=float(domain["north"]),
                spacing=float(payload["flexpart"]["grid_spacing_degrees"]),
            ),
            deposition=FlexpartDeposition(
                wet=deposition["wet"],
                dry=deposition["dry"],
                settling=deposition["settling"],
            ),
            particle_budget_per_species_day=int(
                payload["flexpart"]["particle_budget_per_species_day"]
            ),
            minimum_particles_per_release=int(
                payload["flexpart"]["minimum_particles_per_release"]
            ),
            maximum_releases=int(payload["flexpart"]["maximum_releases"]),
            threads=int(payload["flexpart"]["threads"]),
            base_random_seed=int(payload["flexpart"]["base_random_seed"]),
        )


def dominant_event_fuel(
    event: dict[str, Any],
    crosswalk: dict[str, str],
) -> tuple[FbpFuel, dict[str, int]]:
    """Resolve a unique modal FBP fuel without using model performance."""

    counts = Counter(
        str(detection.get("model_fuel") or detection.get("fuel") or "").upper()
        for detection in event["detections"]
    )
    counts.pop("", None)
    if not counts:
        raise ValueError(f"event {event['event_id']} has no fuel observations")
    maximum = max(counts.values())
    modes = sorted(name for name, count in counts.items() if count == maximum)
    if len(modes) != 1:
        raise ValueError(f"event {event['event_id']} has tied dominant fuels: {modes}")
    resolved = resolve_fbp_fuel(modes[0], crosswalk)
    if resolved is None:
        raise ValueError(f"event {event['event_id']} has unsupported dominant fuel {modes[0]}")
    return resolved, dict(sorted(counts.items()))


def _load_inputs(
    *,
    event_area_path: Path,
    events_path: Path,
    config: CandidateConfig,
    crosswalk_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any], dict[str, Any]]:
    area_payload = json.loads(event_area_path.read_text(encoding="utf-8"))
    if area_payload.get("operator_version") != config.area_operator_version:
        raise ValueError("event-area report uses a different observation operator")
    event_payload = json.loads(events_path.read_text(encoding="utf-8"))
    events_by_id = {item["event_id"]: item for item in event_payload["events"]}
    selected: list[dict[str, Any]] = []
    for area_event in area_payload["events"]:
        if not area_event["burned_area_eligible"]:
            continue
        event_id = area_event["event_id"]
        if event_id not in events_by_id:
            raise ValueError(f"area-qualified event is absent from frozen events: {event_id}")
        daily = area_event["daily_area"][config.area_curve]
        if not daily or any(float(value) < 0 for value in daily.values()):
            raise ValueError(f"area-qualified event has an invalid daily area curve: {event_id}")
        positive_daily = {
            day: float(value)
            for day, value in sorted(daily.items())
            if float(value) > 0
        }
        if not positive_daily:
            raise ValueError(
                f"area-qualified event has no positive area in the selected curve: {event_id}"
            )
        selected.append(
            {
                "event": events_by_id[event_id],
                "area": area_event,
                "daily_increment_ha": positive_daily,
            }
        )
    if not selected:
        raise ValueError("no independently area-qualified event is available")
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    if crosswalk_payload.get("schema_version") != 1:
        raise ValueError("unsupported fuel crosswalk")
    crosswalk = {
        str(key).upper(): str(value).upper()
        for key, value in crosswalk_payload["rules"].items()
    }
    return selected, crosswalk, area_payload, event_payload


def _gfs_manifest(data_root: Path, source_day: date) -> Path:
    path = (
        data_root
        / "raw/noaa/gfs/global_1p00"
        / f"{source_day:%Y/%m/%d}"
        / "00/manifest.json"
    )
    if not path.is_file():
        raise FileNotFoundError(f"missing daily GFS cycle: {path}")
    return path


def _source_interval(source_day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(source_day, datetime_time(), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _event_day_seed(base: int, source_day: date, first_day: date) -> int:
    offset = (source_day - first_day).days * 10
    value = base + offset
    if not 1 <= value <= 2_147_483_647:
        raise ValueError("derived event-day base seed is outside the supported range")
    return value


def run_validation_candidate(
    *,
    data_root: Path,
    event_area_path: Path,
    events_path: Path,
    candidate_config_path: Path,
    crosswalk_path: Path,
    emission_factors_path: Path,
    cffeps_executable: Path,
    flexpart_root: Path,
    flexpart_executable: Path,
    output_directory: Path,
    run_transport: bool = True,
    transport_workers: int = 1,
) -> dict[str, Any]:
    """Run the frozen central emissions and isolated daily transport members."""

    if not 1 <= transport_workers <= 8:
        raise ValueError("transport_workers must be in [1, 8]")
    config = CandidateConfig.from_yaml(candidate_config_path)
    selected, crosswalk, area_payload, event_payload = _load_inputs(
        event_area_path=event_area_path,
        events_path=events_path,
        config=config,
        crosswalk_path=crosswalk_path,
    )
    data_root = data_root.resolve()
    output_directory = output_directory.resolve()
    started = time.perf_counter()
    area_qualified_event_count = len(selected)

    eligible: list[dict[str, Any]] = []
    input_events: list[dict[str, Any]] = []
    selection_exclusions: list[dict[str, Any]] = []
    for item in selected:
        event = item["event"]
        try:
            fuel, fuel_counts = dominant_event_fuel(event, crosswalk)
        except ValueError as exc:
            selection_exclusions.append(
                {
                    "event_id": event["event_id"],
                    "reason": "nonunique_or_unsupported_dominant_fuel",
                    "detail": str(exc),
                }
            )
            continue
        west, south, east, north = (
            config.domain.west,
            config.domain.south,
            config.domain.east,
            config.domain.north,
        )
        if not (
            west <= float(event["longitude"]) <= east
            and south <= float(event["latitude"]) <= north
        ):
            raise ValueError(
                "selected event lies outside frozen candidate domain: "
                f"{event['event_id']}"
            )
        fire_weather_by_day: dict[str, dict[str, Any]] = {}
        fire_weather_failures: list[dict[str, str]] = []
        if config.require_complete_fire_weather:
            for day_text in item["daily_increment_ha"]:
                try:
                    fire_weather_by_day[day_text] = sample_fire_weather(
                        data_root,
                        date.fromisoformat(day_text),
                        float(event["latitude"]),
                        float(event["longitude"]),
                    )
                except (FileNotFoundError, ValueError) as exc:
                    fire_weather_failures.append(
                        {
                            "source_day": day_text,
                            "error_type": type(exc).__name__,
                            "detail": str(exc),
                        }
                    )
        if fire_weather_failures:
            selection_exclusions.append(
                {
                    "event_id": event["event_id"],
                    "reason": "incomplete_required_cwfis_fire_weather",
                    "affected_source_days": fire_weather_failures,
                }
            )
            continue
        item["fuel"] = fuel
        item["fire_weather_by_day"] = fire_weather_by_day
        eligible.append(item)
        input_event = {
            "event_id": event["event_id"],
            "latitude": event["latitude"],
            "longitude": event["longitude"],
            "fuel_counts": fuel_counts,
            "selected_fuel": fuel.model_code,
            "fuel_parameter_source": fuel.parameter_source,
            "daily_increment_ha": item["daily_increment_ha"],
        }
        if config.require_complete_fire_weather:
            input_event["fire_weather_by_source_day"] = fire_weather_by_day
        input_events.append(input_event)
    selected = eligible
    if not selected:
        raise ValueError("no candidate event has every required frozen input")

    output_directory.mkdir(parents=True, exist_ok=False)
    source_days = sorted(
        {
            date.fromisoformat(day)
            for item in selected
            for day in item["daily_increment_ha"]
        }
    )
    first_source_day = min(source_days)
    input_manifest = {
        "schema_version": 1,
        "candidate_version": config.candidate_version,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "candidate_config": {
            "path": candidate_config_path.as_posix(),
            "sha256": _sha256(candidate_config_path),
            "sources": [
                {
                    "path": source.as_posix(),
                    "sha256": _sha256(source),
                }
                for source in config.source_paths
            ],
        },
        "event_area_report": {
            "path": event_area_path.as_posix(),
            "sha256": _sha256(event_area_path),
            "operator_version": area_payload["operator_version"],
        },
        "frozen_events": {
            "path": events_path.as_posix(),
            "sha256": _sha256(events_path),
            "algorithm_version": event_payload["algorithm_version"],
        },
        "fuel_crosswalk": {
            "path": crosswalk_path.as_posix(),
            "sha256": _sha256(crosswalk_path),
        },
        "emission_factors": {
            "path": emission_factors_path.as_posix(),
            "sha256": _sha256(emission_factors_path),
        },
        "executables": {
            "cffeps": {
                "path": cffeps_executable.resolve().as_posix(),
                "sha256": _sha256(cffeps_executable),
            },
            "flexpart": {
                "path": flexpart_executable.resolve().as_posix(),
                "sha256": _sha256(flexpart_executable),
            },
        },
        "area_qualified_event_count": area_qualified_event_count,
        "event_count": len(selected),
        "selection_exclusion_count": len(selection_exclusions),
        "selection_exclusions": selection_exclusions,
        "require_complete_fire_weather": config.require_complete_fire_weather,
        "event_day_count": sum(len(item["daily_increment_ha"]) for item in selected),
        "source_days": [value.isoformat() for value in source_days],
        "events": input_events,
        "daily_area_allocation": config.daily_area_allocation,
        "phase_tail_policy": config.phase_tail_policy,
        "mass_balance_accounting": config.mass_balance_accounting,
        "area_curve": config.area_curve,
        "emission_factor_uncertainty": config.emission_factor_uncertainty,
        "vertical_profile_algorithm": config.vertical_profile_algorithm,
        "deposition": {
            "wet": config.deposition.wet,
            "dry": config.deposition.dry,
            "settling": config.deposition.settling,
        },
        "execution": {
            "transport_member_workers": transport_workers if run_transport else 0,
            "threads_per_member": config.threads,
            "scientific_members_are_independent": True,
        },
    }
    _atomic_json(output_directory / "input-manifest.json", input_manifest)

    all_rows: list[EmissionRow] = []
    cffeps_manifests: list[dict[str, Any]] = []
    for item in selected:
        event = item["event"]
        fuel: FbpFuel = item["fuel"]
        for day_text, daily_area_ha in item["daily_increment_ha"].items():
            source_day = date.fromisoformat(day_text)
            source_start, source_end = _source_interval(source_day)
            gfs_manifest = _gfs_manifest(data_root, source_day)
            profiles, profile_provenance = extract_cycle_profiles(
                gfs_manifest,
                float(event["latitude"]),
                float(event["longitude"]),
            )
            profiles = [
                profile
                for profile in profiles
                if source_start <= profile.valid_time < source_end
            ]
            if len(profiles) != 24:
                raise ValueError(f"GFS cycle does not provide 24 source hours on {source_day}")
            fire_weather = item["fire_weather_by_day"].get(day_text)
            if fire_weather is None:
                fire_weather = sample_fire_weather(
                    data_root,
                    source_day,
                    float(event["latitude"]),
                    float(event["longitude"]),
                )
            fire = CffepsFire(
                event_id=str(event["event_id"]),
                latitude=float(event["latitude"]),
                longitude=float(event["longitude"]),
                fuel_type=fuel.model_code,
                estimated_area_ha=daily_area_ha,
                detected_at=source_start
                + timedelta(hours=config.nominal_detection_hour_utc),
                ffmc=float(fire_weather["ffmc"]),
                dmc=float(fire_weather["dmc"]),
                dc=float(fire_weather["dc"]),
                percent_conifer=fuel.percent_conifer,
                percent_dead_fir=fuel.percent_dead_fir,
                grass_curing_percent=fuel.grass_curing_percent,
            )
            event_day_id = f"{config.candidate_version}:{event['event_id']}:{source_day}"
            rows, manifest = run_cffeps(
                run_id=event_day_id,
                fire=fire,
                profiles=profiles,
                executable=cffeps_executable,
                work_dir=(
                    output_directory
                    / "cffeps"
                    / source_day.isoformat()
                    / str(event["event_id"])
                ),
                emission_factors_path=emission_factors_path,
                species=config.species,
                uncertainty=config.emission_factor_uncertainty,
                vertical_layer_count=config.vertical_layer_count,
                vertical_profile_algorithm=config.vertical_profile_algorithm,
            )
            rows, area_manifest = apply_cumulative_area_curve(
                rows,
                ((source_start, 0.0), (source_end, daily_area_ha)),
                conserve_active_intervals=(
                    config.daily_area_allocation
                    == "linear_utc_daily_total_conserved_over_active_cffeps_intervals_v1"
                ),
            )
            manifest.update(area_manifest)
            manifest.update(
                {
                    "event_day_id": event_day_id,
                    "mcd64a1_daily_increment_ha": daily_area_ha,
                    "mcd64a1_event_area_report_sha256": _sha256(event_area_path),
                    "fuel_selection": {
                        "algorithm": "unique_modal_frozen_detection_fuel_v1",
                        "model_code": fuel.model_code,
                        "parameter_source": fuel.parameter_source,
                    },
                    "fire_weather": fire_weather,
                    "meteorology": profile_provenance,
                }
            )
            manifest["mass_kg_by_species"] = {
                species: sum(row.emitted_mass_kg for row in rows if row.species == species)
                for species in config.species
            }
            all_rows.extend(rows)
            cffeps_manifests.append(manifest)

    mass_by_species = {
        species: sum(row.emitted_mass_kg for row in all_rows if row.species == species)
        for species in config.species
    }
    emission_manifest = {
        "schema_version": 1,
        "candidate_version": config.candidate_version,
        "event_count": len(selected),
        "event_day_count": len(cffeps_manifests),
        "source_days": [value.isoformat() for value in source_days],
        "cffeps_runs": cffeps_manifests,
        "mass_kg_by_species": mass_by_species,
        "phase_tail_policy": config.phase_tail_policy,
        "mass_balance_accounting": config.mass_balance_accounting,
    }
    emissions_path = output_directory / "input/emissions.nc"
    final_emission_manifest = write_emission_bundle(
        emissions_path,
        all_rows,
        emission_manifest,
    )
    bundle_validation = validate_emission_bundle(emissions_path)

    transport_days: dict[str, Any] = {}
    if run_transport:
        limits = FlexpartRunLimits(
            timeout_seconds=10_800,
            maximum_output_bytes=10 * 1024**3,
            maximum_releases=config.maximum_releases,
            minimum_particles_per_release=config.minimum_particles_per_release,
            threads=config.threads,
        )
        rows_by_day: dict[date, list[EmissionRow]] = defaultdict(list)
        for row in all_rows:
            rows_by_day[row.source_time_start.astimezone(UTC).date()].append(row)
        prepared_days: dict[str, dict[str, Any]] = {}
        transport_jobs: list[tuple[str, str, Path, int]] = []
        for source_day in source_days:
            source_start, source_end = _source_interval(source_day)
            day_directory = output_directory / "transport" / source_day.isoformat()
            prepared = prepare_species_runs(
                parent_dir=day_directory,
                flexpart_root=flexpart_root,
                gfs_manifest=_gfs_manifest(data_root, source_day),
                rows=rows_by_day[source_day],
                species=config.species,
                start=source_start,
                end=source_end,
                domain=config.domain,
                particle_budget_per_species=config.particle_budget_per_species_day,
                limits=limits,
                deposition=config.deposition,
            )
            day_base_seed = _event_day_seed(
                config.base_random_seed,
                source_day,
                first_source_day,
            )
            day_text = source_day.isoformat()
            prepared_days[day_text] = prepared
            for species in config.species:
                transport_jobs.append(
                    (
                        day_text,
                        species,
                        day_directory / species.lower(),
                        derive_member_random_seed(day_base_seed, species),
                    )
                )

        results_by_day: dict[str, dict[str, Any]] = defaultdict(dict)
        if transport_workers == 1:
            for day_text, species, run_directory, random_seed in transport_jobs:
                results_by_day[day_text][species] = run_flexpart(
                    run_directory,
                    flexpart_executable,
                    limits,
                    random_seed=random_seed,
                )
        else:
            with ProcessPoolExecutor(max_workers=transport_workers) as executor:
                futures = {
                    executor.submit(
                        run_flexpart,
                        run_directory,
                        flexpart_executable,
                        limits,
                        random_seed=random_seed,
                    ): (day_text, species)
                    for day_text, species, run_directory, random_seed in transport_jobs
                }
                for future in as_completed(futures):
                    day_text, species = futures[future]
                    results_by_day[day_text][species] = future.result()

        for source_day in source_days:
            day_text = source_day.isoformat()
            day_manifest = {
                "schema_version": 1,
                "candidate_version": config.candidate_version,
                "source_day": day_text,
                "prepared_members": prepared_days[day_text],
                "results": {
                    species: results_by_day[day_text][species]
                    for species in config.species
                },
            }
            day_directory = output_directory / "transport" / day_text
            _atomic_json(day_directory / "manifest.json", day_manifest)
            transport_days[day_text] = day_manifest

    manifest = {
        "schema_version": 1,
        "candidate_version": config.candidate_version,
        "status": "complete" if run_transport else "emissions_complete",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "input_manifest": {
            "path": (output_directory / "input-manifest.json").as_posix(),
            "sha256": _sha256(output_directory / "input-manifest.json"),
        },
        "emissions": final_emission_manifest["bundle"],
        "bundle_validation": bundle_validation,
        "mass_kg_by_species": mass_by_species,
        "transport_days": transport_days,
        "execution": {
            "transport_member_workers": transport_workers if run_transport else 0,
            "threads_per_member": config.threads,
        },
    }
    _atomic_json(output_directory / "manifest.json", manifest)
    return manifest | {
        "manifest_path": (output_directory / "manifest.json").as_posix(),
        "manifest_sha256": _sha256(output_directory / "manifest.json"),
        "emissions_path": emissions_path.as_posix(),
    }
