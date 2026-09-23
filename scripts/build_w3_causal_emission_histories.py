#!/usr/bin/env python3
"""Build pre-overpass W3 source histories without FLEXPART or height access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from weather_ingest.gfs_profiles import extract_cycle_profiles
from weather_ingest.w3_causal_history import (
    area_partition,
    latest_available_state,
    parse_utc,
    segment_boundaries,
    source_records,
    uniform_area_for_interval,
    utc_text,
    verify_causality,
)

OPERATOR_VERSION = "w3-pre-overpass-causal-source-history-v1"
AREA_FIELDS = {
    "central": "central_daily_increment_ha",
    "high_confidence": "high_confidence_daily_increment_ha",
    "earliest_timing": "earliest_timing_daily_increment_ha",
    "latest_timing": "latest_timing_daily_increment_ha",
}


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


def year_paths(values: list[str]) -> dict[int, Path]:
    result = {}
    for value in values:
        year_text, separator, path_text = value.partition("=")
        if not separator:
            raise ValueError(f"expected YEAR=PATH: {value}")
        result[int(year_text)] = Path(path_text).resolve()
    return result


def load_firem3_rows(path: Path, year: int, dates: set[str]) -> list[dict[str, str]]:
    member = f"{year}_hotspots.csv"
    with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
        return [
            dict(row)
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            if row["rep_date"][:10] in dates
        ]


def profile_for_time(
    profiles_by_time: dict[datetime, Any],
    when: datetime,
) -> Any:
    key = when.replace(minute=0, second=0, microsecond=0)
    if key not in profiles_by_time:
        raise ValueError(f"historical GFS profiles do not cover {when.isoformat()}")
    return profiles_by_time[key]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignment-ledger", type=Path, required=True)
    parser.add_argument("--gfs-ledger", type=Path, required=True)
    parser.add_argument(
        "--hotspots",
        action="append",
        default=[],
        help="YEAR=PATH to annual Fire M3 ZIP",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--history-hours", type=int, default=24)
    parser.add_argument("--state-lookback-hours", type=int, default=24)
    parser.add_argument("--maximum-fire-distance-km", type=float, default=5.0)
    args = parser.parse_args()
    if args.history_hours != 24 or args.state_lookback_hours < 0:
        parser.error("formal v1 uses a 24-hour history and nonnegative state lookback")

    assignment_path = args.assignment_ledger.resolve()
    gfs_path = args.gfs_ledger.resolve()
    output_directory = args.output_directory.resolve()
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    gfs = json.loads(gfs_path.read_text(encoding="utf-8"))
    gfs_by_overpass = {str(record["overpass_id"]): record for record in gfs["records"]}
    hotspot_paths = year_paths(args.hotspots)

    contexts = []
    required_dates: dict[int, set[str]] = {year: set() for year in hotspot_paths}
    for item in assignment["assignments"]:
        if item["status"] == "excluded_input_invalid":
            continue
        fire = json.loads(Path(item["fire_assignment"]["path"]).read_text())
        overpass = parse_utc(fire["selected_source"]["observed_at_utc"])
        evidence_start = overpass - timedelta(hours=args.history_hours + args.state_lookback_hours)
        cursor = evidence_start.date()
        while cursor <= overpass.date():
            required_dates[overpass.year].add(cursor.isoformat())
            cursor += timedelta(days=1)
        contexts.append((item, fire, overpass))
    rows_by_year = {
        year: load_firem3_rows(path, year, required_dates[year])
        for year, path in hotspot_paths.items()
    }

    records = []
    for item in assignment["assignments"]:
        overpass_id = str(item["overpass_id"])
        if item["status"] == "excluded_input_invalid":
            records.append(
                {
                    "overpass_id": overpass_id,
                    "event_id": item.get("event_id"),
                    "status": "excluded_pre_history_input_invalid",
                    "reason": item["exclusion_reason"],
                }
            )
            continue
        fire = json.loads(Path(item["fire_assignment"]["path"]).read_text())
        overpass = parse_utc(fire["selected_source"]["observed_at_utc"])
        history_start = overpass - timedelta(hours=args.history_hours)
        evidence_start = history_start - timedelta(hours=args.state_lookback_hours)
        latitude = float(fire["selected_source"]["latitude"])
        longitude = float(fire["selected_source"]["longitude"])
        evidence = source_records(
            rows_by_year[overpass.year],
            source_latitude=latitude,
            source_longitude=longitude,
            start=evidence_start,
            end=overpass,
            maximum_distance_km=args.maximum_fire_distance_km,
        )
        area_artifact = item["artifacts"]["independent_area"]
        area_payload = json.loads(Path(area_artifact["path"]).read_text())
        daily_area = area_payload["operator_result"]["daily_area"]
        curves = {
            name: {day: float(value) for day, value in daily_area[field].items()}
            for name, field in AREA_FIELDS.items()
        }
        gfs_record = gfs_by_overpass[overpass_id]
        cycle_records = sorted(gfs_record["cycles"], key=lambda cycle: cycle["initialization_time"])
        profiles_by_time = {}
        profile_sources = []
        for cycle in cycle_records:
            manifest = Path(cycle["manifest_path"]).resolve()
            if sha256(manifest) != cycle["manifest_sha256"]:
                raise ValueError(f"GFS manifest hash mismatch: {overpass_id}")
            profiles, provenance = extract_cycle_profiles(manifest, latitude, longitude)
            for profile in profiles:
                # Cycles are ordered oldest to newest.  Overwrite overlapping
                # valid times so each segment uses the latest forecast cycle
                # that had already initialized, rather than an older forecast.
                profiles_by_time[profile.valid_time] = (profile, cycle)
            profile_sources.append(
                {
                    **artifact(manifest),
                    "initialization_time_utc": cycle["initialization_time"],
                    "profile_extraction": provenance,
                }
            )

        boundaries = segment_boundaries(
            start=history_start,
            end=overpass,
            evidence_times=(record["observed_at"] for record in evidence),
        )
        segments = []
        released_totals = {name: 0.0 for name in AREA_FIELDS}
        unavailable_state_totals = {name: 0.0 for name in AREA_FIELDS}
        for start, end in pairwise(boundaries):
            state = latest_available_state(evidence, start)
            profile, cycle = profile_for_time(profiles_by_time, start)
            candidate_area = {
                name: uniform_area_for_interval(curve, start, end) for name, curve in curves.items()
            }
            released_area = {
                name: value if state is not None else 0.0 for name, value in candidate_area.items()
            }
            for name in AREA_FIELDS:
                released_totals[name] += released_area[name]
                unavailable_state_totals[name] += candidate_area[name] - released_area[name]
            segments.append(
                {
                    "start_utc": utc_text(start),
                    "end_utc": utc_text(end),
                    "duration_seconds": (end - start).total_seconds(),
                    "candidate_area_ha": candidate_area,
                    "released_area_ha": released_area,
                    "fire_state": (
                        {
                            "observed_at_utc": utc_text(state["observed_at"]),
                            "age_seconds_at_segment_start": (
                                start - state["observed_at"]
                            ).total_seconds(),
                            "distance_km": state["distance_km"],
                            "ffmc": state["ffmc"],
                            "dmc": state["dmc"],
                            "dc": state["dc"],
                            "sensor": state["sensor"],
                            "source": state["source"],
                            "provider_row_sha256": state["provider_row_sha256"],
                        }
                        if state is not None
                        else None
                    ),
                    "meteorology": {
                        "initialization_time_utc": cycle["initialization_time"],
                        "valid_time_utc": utc_text(profile.valid_time),
                        "latitude": profile.latitude,
                        "longitude": profile.longitude,
                        "specific_humidity_kg_kg": (profile.specific_humidity_kg_kg),
                        "wind_speed_knots": profile.wind_speed_knots,
                        "dewpoint_k": profile.dewpoint_k,
                        "elevation_m": profile.elevation_m,
                        "pressure_pa": list(profile.pressure_pa),
                        "temperature_k": list(profile.temperature_k),
                        "height_m_agl": list(profile.height_m_agl),
                        "manifest_sha256": cycle["manifest_sha256"],
                    },
                }
            )
        partitions = {
            name: area_partition(
                curve,
                history_start=history_start,
                overpass=overpass,
            )
            for name, curve in curves.items()
        }
        causality = verify_causality(overpass=overpass, segments=segments)
        status = (
            "ready_causal_source_history"
            if released_totals["central"] > 0 and all(causality.values())
            else "excluded_no_causal_central_area"
        )
        event_path = output_directory / overpass_id / "causal-source-history.json"
        event_payload = {
            "schema_version": 1,
            "artifact_type": "w3-causal-source-history",
            "operator_version": OPERATOR_VERSION,
            "overpass_id": overpass_id,
            "event_id": item["event_id"],
            "status": status,
            "history_start_utc": utc_text(history_start),
            "overpass_time_utc": utc_text(overpass),
            "source_latitude": latitude,
            "source_longitude": longitude,
            "fuel": json.loads(Path(item["artifacts"]["fuel"]["path"]).read_text()),
            "area_partitions": partitions,
            "released_area_totals_ha": released_totals,
            "area_unreleased_due_to_unavailable_prior_state_ha": (unavailable_state_totals),
            "firem3_evidence_count": len(evidence),
            "first_firem3_evidence_utc": (
                utc_text(evidence[0]["observed_at"]) if evidence else None
            ),
            "last_firem3_evidence_utc": (
                utc_text(evidence[-1]["observed_at"]) if evidence else None
            ),
            "segments": segments,
            "causality_checks": causality,
            "sources": {
                "fire_assignment": item["fire_assignment"],
                "independent_area": area_artifact,
                "fuel": item["artifacts"]["fuel"],
                "gfs_cycles": profile_sources,
                "firem3_archive": artifact(hotspot_paths[overpass.year]),
            },
            "causality_scope": {
                "physical_event_time": (
                    "No released interval, Fire M3 state, or meteorology cycle "
                    "originates after the MISR overpass."
                ),
                "operational_data_availability": (
                    "Not satisfied: final MCD64A1 is a retrospective product "
                    "published after the fire. This history is suitable for a "
                    "retrospective controlled validation, not a claim of real-time "
                    "input availability."
                ),
            },
            "selection_firewall": {
                "misr_height_accessed": False,
                "cffeps_height_accessed": False,
                "flexpart_output_accessed": False,
                "model_performance_accessed": False,
            },
        }
        atomic_json(event_path, event_payload)
        records.append(
            {
                "overpass_id": overpass_id,
                "event_id": item["event_id"],
                "status": status,
                "released_central_area_ha": released_totals["central"],
                "post_overpass_central_area_excluded_ha": partitions["central"][
                    "after_overpass_excluded_ha"
                ],
                "firem3_evidence_count": len(evidence),
                "causality_checks_passed": all(causality.values()),
                "history": artifact(event_path),
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "w3-causal-source-history-ledger",
        "operator_version": OPERATOR_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "complete_input_only_causal_histories",
        "method": {
            "history_hours": args.history_hours,
            "state_lookback_hours": args.state_lookback_hours,
            "maximum_fire_distance_km": args.maximum_fire_distance_km,
            "area_temporal_operator": (
                "uniform within each MCD64A1 UTC burn-date day, clipped to "
                "the pre-overpass 24-hour interval"
            ),
            "state_operator": (
                "latest Fire M3 FFMC/DMC/DC record within 5 km available at "
                "or before each segment start; area is not shifted when state "
                "evidence is unavailable"
            ),
            "meteorology_operator": (
                "00Z GFS cycle initialized at or before the segment, nearest "
                "grid point, hourly interpolation from three-hour fields, "
                "40 log-pressure levels"
            ),
            "post_overpass_information_used": False,
        },
        "sources": {
            "assignment_ledger": artifact(assignment_path),
            "gfs_ledger": artifact(gfs_path),
            "firem3_archives": {
                str(year): artifact(path) for year, path in sorted(hotspot_paths.items())
            },
        },
        "prospective_overpass_count": len(records),
        "ready_causal_history_count": sum(
            item["status"] == "ready_causal_source_history" for item in records
        ),
        "excluded_no_causal_central_area_count": sum(
            item["status"] == "excluded_no_causal_central_area" for item in records
        ),
        "excluded_pre_history_input_invalid_count": sum(
            item["status"] == "excluded_pre_history_input_invalid" for item in records
        ),
        "records": records,
        "selection_firewall": {
            "misr_height_accessed": False,
            "cffeps_height_accessed": False,
            "flexpart_output_accessed": False,
            "model_performance_accessed": False,
        },
    }
    output = args.output_ledger.resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "ready_causal_history_count": payload["ready_causal_history_count"],
                "excluded_no_causal_central_area_count": payload[
                    "excluded_no_causal_central_area_count"
                ],
                "excluded_pre_history_input_invalid_count": payload[
                    "excluded_pre_history_input_invalid_count"
                ],
                "height_or_flexpart_values_emitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
