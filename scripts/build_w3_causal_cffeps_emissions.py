#!/usr/bin/env python3
"""Translate frozen W3 source histories into pre-overpass CFFEPS emissions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
from weather_ingest.fbp_fuels import resolve_fbp_fuel
from weather_ingest.gfs_profiles import AtmosphericProfile
from weather_ingest.w3_causal_history import (
    ceil_utc_hour,
    parse_utc,
    released_area_between,
    segment_at,
    utc_text,
)

OPERATOR_VERSION = "w3-pre-overpass-causal-cffeps-emissions-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def profile_from_segment(segment: dict[str, Any], when: datetime) -> AtmosphericProfile:
    values = segment["meteorology"]
    valid_time = parse_utc(values["valid_time_utc"])
    if valid_time != when or parse_utc(values["initialization_time_utc"]) > when:
        raise ValueError("source history does not provide causal hourly meteorology")
    return AtmosphericProfile(
        valid_time=valid_time,
        latitude=float(values["latitude"]),
        longitude=float(values["longitude"]),
        specific_humidity_kg_kg=float(values["specific_humidity_kg_kg"]),
        wind_speed_knots=float(values["wind_speed_knots"]),
        dewpoint_k=float(values["dewpoint_k"]),
        elevation_m=float(values["elevation_m"]),
        pressure_pa=tuple(float(value) for value in values["pressure_pa"]),
        temperature_k=tuple(float(value) for value in values["temperature_k"]),
        height_m_agl=tuple(float(value) for value in values["height_m_agl"]),
    )


def hourly_inputs(
    history: dict[str, Any],
) -> tuple[
    list[AtmosphericProfile],
    list[tuple[float, float, float]],
    tuple[tuple[datetime, float], ...],
    dict[str, float],
]:
    """Build conservative hourly inputs; omitted area is never shifted."""

    history_start = parse_utc(history["history_start_utc"])
    overpass = parse_utc(history["overpass_time_utc"])
    cursor = ceil_utc_hour(history_start)
    last_hour = overpass.replace(minute=0, second=0, microsecond=0)
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    while cursor <= last_hour:
        segment = segment_at(history["segments"], cursor)
        if segment is not None:
            candidates.append((cursor, segment))
        cursor += timedelta(hours=1)
    first_with_state = next(
        (
            index
            for index, (_when, segment) in enumerate(candidates)
            if segment["fire_state"] is not None
        ),
        None,
    )
    if first_with_state is None:
        return (
            [],
            [],
            (),
            {
                "history_released_area_ha": released_area_between(
                    history["segments"],
                    start=history_start,
                    end=overpass,
                ),
                "represented_area_ha": 0.0,
                "unrepresented_subhour_or_missing_state_area_ha": (
                    released_area_between(
                        history["segments"],
                        start=history_start,
                        end=overpass,
                    )
                ),
            },
        )
    selected = candidates[first_with_state:]
    start = selected[0][0]
    profiles = []
    states = []
    for when, segment in selected:
        state = segment["fire_state"]
        if state is None:
            raise ValueError("fire-weather state regressed after becoming available")
        if parse_utc(state["observed_at_utc"]) > when:
            raise ValueError("hourly CFFEPS state uses a future observation")
        profiles.append(profile_from_segment(segment, when))
        states.append(
            (
                float(state["ffmc"]),
                float(state["dmc"]),
                float(state["dc"]),
            )
        )
    if len(profiles) > 24:
        raise ValueError("causal W3 CFFEPS history exceeds the 24-hour driver")

    end = profiles[-1].valid_time + timedelta(hours=1)
    boundaries = [profile.valid_time for profile in profiles] + [end]
    area_curve = tuple(
        (
            boundary,
            released_area_between(
                history["segments"],
                start=start,
                end=min(boundary, overpass),
            ),
        )
        for boundary in boundaries
    )
    represented = area_curve[-1][1]
    history_area = released_area_between(
        history["segments"],
        start=history_start,
        end=overpass,
    )
    return (
        profiles,
        states,
        area_curve,
        {
            "history_released_area_ha": history_area,
            "represented_area_ha": represented,
            "unrepresented_subhour_or_missing_state_area_ha": max(
                history_area - represented,
                0.0,
            ),
        },
    )


def clip_at_overpass(
    rows: list[EmissionRow],
    overpass: datetime,
) -> list[EmissionRow]:
    clipped = []
    for row in rows:
        if row.source_time_start >= overpass:
            continue
        end = min(row.source_time_end, overpass)
        duration = (end - row.source_time_start).total_seconds()
        if duration <= 0:
            continue
        clipped.append(
            replace(
                row,
                source_time_end=end,
                emission_rate_kg_s=row.emitted_mass_kg / duration,
                quality_flags=(
                    f"{row.quality_flags};strictly_pre_overpass_v1"
                    + (
                        ";partial_final_hour_clipped_at_overpass"
                        if end < row.source_time_end
                        else ""
                    )
                ),
            )
        )
    return clipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--causal-history-ledger", type=Path, required=True)
    parser.add_argument("--cffeps-executable", type=Path, required=True)
    parser.add_argument("--emission-factors", type=Path, required=True)
    parser.add_argument("--fuel-crosswalk", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--vertical-layer-count", type=int, default=12)
    args = parser.parse_args()

    source_ledger_path = args.causal_history_ledger.resolve()
    source_ledger = json.loads(source_ledger_path.read_text(encoding="utf-8"))
    if (
        source_ledger.get("artifact_type") != "w3-causal-source-history-ledger"
        or source_ledger["selection_firewall"]["flexpart_output_accessed"]
    ):
        raise ValueError("invalid causal W3 source-history ledger")
    executable = args.cffeps_executable.resolve()
    factors = args.emission_factors.resolve()
    crosswalk_path = args.fuel_crosswalk.resolve()
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk = {
        str(key).upper(): str(value).upper() for key, value in crosswalk_payload["rules"].items()
    }
    output_directory = args.output_directory.resolve()
    records = []
    for source_record in source_ledger["records"]:
        overpass_id = source_record["overpass_id"]
        if source_record["status"] != "ready_causal_source_history":
            records.append(
                {
                    "overpass_id": overpass_id,
                    "event_id": source_record.get("event_id"),
                    "status": "excluded_by_causal_source_history",
                    "reason": source_record["status"],
                }
            )
            continue
        history_path = Path(source_record["history"]["path"]).resolve()
        if sha256(history_path) != source_record["history"]["sha256"]:
            raise ValueError(f"causal source-history hash changed: {overpass_id}")
        history = json.loads(history_path.read_text(encoding="utf-8"))
        profiles, states, area_curve, coverage = hourly_inputs(history)
        if not profiles or coverage["represented_area_ha"] <= 0:
            records.append(
                {
                    "overpass_id": overpass_id,
                    "event_id": source_record["event_id"],
                    "status": "excluded_no_hourly_causal_emission_input",
                    "coverage": coverage,
                }
            )
            continue

        fuel_payload = history["fuel"]
        fuel = resolve_fbp_fuel(fuel_payload["provider_fuel"], crosswalk)
        if fuel is None:
            raise ValueError(f"unsupported frozen fuel for {overpass_id}")
        first_state = states[0]
        detection = parse_utc(history["first_firem3_evidence_utc"])
        fire = CffepsFire(
            event_id=history["event_id"],
            latitude=float(history["source_latitude"]),
            longitude=float(history["source_longitude"]),
            fuel_type=fuel.model_code,
            estimated_area_ha=coverage["represented_area_ha"],
            detected_at=detection,
            ffmc=first_state[0],
            dmc=first_state[1],
            dc=first_state[2],
            percent_conifer=fuel.percent_conifer,
            percent_dead_fir=fuel.percent_dead_fir,
            grass_curing_percent=fuel.grass_curing_percent,
        )
        event_directory = output_directory / overpass_id
        run_id = f"w3-causal:{overpass_id}"
        rows, cffeps_manifest = run_cffeps(
            run_id=run_id,
            fire=fire,
            profiles=profiles,
            executable=executable,
            work_dir=event_directory / "cffeps",
            emission_factors_path=factors,
            species=("PM25", "CO", "BC"),
            uncertainty="central",
            vertical_layer_count=args.vertical_layer_count,
            vertical_profile_algorithm="cffeps_top_beta_v1",
            fire_weather_states=states,
            estimated_area_states_ha=[
                float(area_curve[index + 1][1]) for index in range(len(profiles))
            ],
        )
        rows, area_manifest = apply_cumulative_area_curve(
            rows,
            area_curve,
            conserve_active_intervals=False,
        )
        overpass = parse_utc(history["overpass_time_utc"])
        rows = clip_at_overpass(rows, overpass)
        if any(row.source_time_end > overpass for row in rows):
            raise ValueError(f"post-overpass CFFEPS row survived: {overpass_id}")
        mass_by_species = {
            species: sum(row.emitted_mass_kg for row in rows if row.species == species)
            for species in ("PM25", "CO", "BC")
        }
        manifest = {
            "schema_version": 1,
            "artifact_type": "w3-causal-cffeps-emission-history",
            "operator_version": OPERATOR_VERSION,
            "overpass_id": overpass_id,
            "event_id": history["event_id"],
            "history_start_utc": history["history_start_utc"],
            "cffeps_start_utc": utc_text(profiles[0].valid_time),
            "overpass_time_utc": history["overpass_time_utc"],
            "last_emission_end_utc": (
                utc_text(max(row.source_time_end for row in rows)) if rows else None
            ),
            "species": ["PM25", "CO", "BC"],
            "mass_kg_by_species": mass_by_species,
            "coverage": coverage,
            "hourly_fire_weather_state_count": len(states),
            "causal_source_history": artifact(history_path),
            "cffeps": cffeps_manifest,
            "area_scaling": area_manifest,
            "temporal_policy": {
                "model_step": "one UTC hour",
                "initial_partial_hour": ("omitted, not shifted to a later or earlier interval"),
                "final_partial_hour": (
                    "area curve is flat after overpass and release interval is "
                    "clipped exactly at overpass"
                ),
                "active_interval_conservation": False,
                "hourly_estimated_area": (
                    "cumulative released area only through the end of the corresponding source hour"
                ),
                "reason": (
                    "redistributing area from an inactive CFFEPS interval could "
                    "move later evidence into an earlier emission"
                ),
            },
            "selection_firewall": {
                "misr_observation_ledger_accessed": False,
                "misr_height_accessed": False,
                "flexpart_output_accessed": False,
                "post_overpass_source_information_used": False,
            },
        }
        bundle_path = event_directory / "emissions.nc"
        final_manifest = write_emission_bundle(bundle_path, rows, manifest)
        validation = validate_emission_bundle(bundle_path)
        manifest_path = bundle_path.with_suffix(".manifest.json")
        records.append(
            {
                "overpass_id": overpass_id,
                "event_id": history["event_id"],
                "status": "ready_causal_cffeps_emission_history",
                "row_count": int(validation["row_count"]),
                "mass_kg_by_species": mass_by_species,
                "coverage": coverage,
                "all_emissions_end_no_later_than_overpass": True,
                "emission_bundle": artifact(bundle_path),
                "manifest": artifact(manifest_path),
                "manifest_bundle_sha256": final_manifest["bundle"]["sha256"],
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "w3-causal-cffeps-emission-history-ledger",
        "operator_version": OPERATOR_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "exploratory_input_only_not_formal_w3_execution",
        "sources": {
            "causal_history_ledger": artifact(source_ledger_path),
            "cffeps_executable": artifact(executable),
            "emission_factors": artifact(factors),
            "fuel_crosswalk": artifact(crosswalk_path),
        },
        "ready_emission_history_count": sum(
            record["status"] == "ready_causal_cffeps_emission_history" for record in records
        ),
        "excluded_count": sum(
            record["status"] != "ready_causal_cffeps_emission_history" for record in records
        ),
        "records": records,
        "selection_firewall": {
            "misr_observation_ledger_accessed": False,
            "misr_height_accessed": False,
            "flexpart_output_accessed": False,
            "post_overpass_source_information_used": False,
        },
        "formal_w3_execution_permitted": False,
    }
    output = args.output_ledger.resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "ready_emission_history_count": payload["ready_emission_history_count"],
                "excluded_count": payload["excluded_count"],
                "height_or_flexpart_values_emitted": False,
                "formal_w3_execution_permitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
