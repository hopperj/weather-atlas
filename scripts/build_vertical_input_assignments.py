#!/usr/bin/env python3
"""Build performance-blind fire/input assignments for the frozen W3 cohort."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from weather_ingest.fbp_fuels import resolve_fbp_fuel

ASSIGNMENT_METHOD = "firem3-location-time-frozen-source-v1"
MAXIMUM_DISTANCE_KM = 5.0
MAXIMUM_TIME_OFFSET_HOURS = 3.0
REQUIRED_NUMERIC_FIELDS = ("ffmc", "dmc", "dc")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"timestamp lacks a UTC offset: {value}")
    return result.astimezone(UTC)


def haversine_km(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    first_latitude_rad, second_latitude_rad = map(math.radians, (first_latitude, second_latitude))
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    value = (
        math.sin(latitude_delta / 2.0) ** 2
        + math.cos(first_latitude_rad)
        * math.cos(second_latitude_rad)
        * math.sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * 6371.0088 * math.asin(math.sqrt(value))


def provider_row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fire_event_id(row: dict[str, str]) -> str:
    identity = "|".join(
        (
            row["rep_date"].strip(),
            f"{float(row['lat']):.5f}",
            f"{float(row['lon']):.5f}",
            row["sensor"].strip(),
            row["source"].strip(),
        )
    )
    return "w3-fire-" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def load_hotspots(
    archive_path: Path,
    *,
    year: int,
    required_dates: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not zipfile.is_zipfile(archive_path):
        raise ValueError(f"Fire M3 input is not a ZIP archive: {archive_path}")
    member = f"{year}_hotspots.csv"
    rows: list[dict[str, str]] = []
    scanned = 0
    with zipfile.ZipFile(archive_path) as archive:
        if member not in archive.namelist():
            raise ValueError(f"Fire M3 archive lacks {member}")
        with archive.open(member) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            required = {
                "rep_date",
                "lat",
                "lon",
                "country",
                "sensor",
                "source",
                "fuel",
                *REQUIRED_NUMERIC_FIELDS,
            }
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Fire M3 archive lacks fields: {sorted(missing)}")
            for row in reader:
                scanned += 1
                if row["country"].strip().upper() == "C" and row["rep_date"][:10] in required_dates:
                    rows.append(dict(row))
    return rows, {
        **artifact(archive_path),
        "csv_member": member,
        "annual_rows_scanned": scanned,
        "candidate_date_rows": len(rows),
    }


def plume_source_groups(overpass: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for plume in overpass["plumes"]:
        key = (
            str(plume["p_date"]),
            str(plume["p_src_lat"]),
            str(plume["p_src_long"]),
        )
        grouped.setdefault(key, []).append(plume)
    return [
        {
            "observed_at_utc": key[0],
            "latitude": float(key[1]),
            "longitude": float(key[2]),
            "plumes": sorted(values, key=lambda item: str(item["p_name"])),
        }
        for key, values in sorted(grouped.items())
    ]


def finite_fire_state(row: dict[str, str]) -> bool:
    try:
        return all(math.isfinite(float(row[field])) for field in REQUIRED_NUMERIC_FIELDS)
    except ValueError:
        return False


def select_assignment(
    overpass: dict[str, Any],
    hotspots: list[dict[str, str]],
    fuel_crosswalk: dict[str, str],
) -> dict[str, Any] | None:
    candidates = []
    for group in plume_source_groups(overpass):
        observed = parse_time(group["observed_at_utc"])
        for row in hotspots:
            provider_time = datetime.strptime(row["rep_date"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=UTC
            )
            time_offset_hours = abs((provider_time - observed).total_seconds()) / 3600.0
            if time_offset_hours > MAXIMUM_TIME_OFFSET_HOURS:
                continue
            distance_km = haversine_km(
                group["latitude"],
                group["longitude"],
                float(row["lat"]),
                float(row["lon"]),
            )
            if distance_km > MAXIMUM_DISTANCE_KM:
                continue
            resolved = resolve_fbp_fuel(row["fuel"].strip(), fuel_crosswalk)
            if resolved is None or not finite_fire_state(row):
                continue
            candidates.append(
                {
                    "group": group,
                    "row": row,
                    "distance_km": distance_km,
                    "time_offset_hours": time_offset_hours,
                    "resolved_fuel": resolved.model_code,
                    "rank": (
                        round(distance_km, 9),
                        round(time_offset_hours, 9),
                        str(group["plumes"][0]["p_name"]),
                        provider_row_hash(row),
                    ),
                }
            )
    if not candidates:
        return None
    return min(candidates, key=lambda item: item["rank"])


def load_year_map(values: list[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for value in values:
        year_text, separator, path_text = value.partition("=")
        if not separator:
            raise ValueError(f"expected YEAR=PATH, received {value}")
        year = int(year_text)
        if year in result:
            raise ValueError(f"duplicate year mapping: {year}")
        result[year] = Path(path_text).expanduser().resolve()
    return result


def load_area_results(paths: dict[int, Path]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for year, path in paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for event in payload["events"]:
            if event["event_id"] in results:
                raise ValueError(f"duplicate MCD64A1 event result: {event['event_id']}")
            results[event["event_id"]] = {
                "year": year,
                "source": artifact(path),
                "result": event,
            }
    return results


def load_transport_results(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("transport ledger lacks a records list")
    return {str(record["overpass_id"]): record for record in records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertical-ledger", type=Path, required=True)
    parser.add_argument(
        "--hotspots",
        action="append",
        default=[],
        help="YEAR=PATH to a CWFIS annual hotspot ZIP; repeat per year",
    )
    parser.add_argument(
        "--hotspot-manifest",
        action="append",
        default=[],
        help="YEAR=PATH to the acquisition manifest; repeat per year",
    )
    parser.add_argument(
        "--mcd64-area-results",
        action="append",
        default=[],
        help="YEAR=PATH to an event-area result; optional and repeatable",
    )
    parser.add_argument("--transport-ledger", type=Path)
    parser.add_argument(
        "--fuel-crosswalk",
        type=Path,
        default=Path("config/smoke/fuel_crosswalk.yaml"),
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--assignment-ledger", type=Path, required=True)
    args = parser.parse_args()

    vertical_path = args.vertical_ledger.expanduser().resolve()
    output = args.output_directory.expanduser().resolve()
    vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
    if vertical.get("artifact_type") != "w1-input-only-misr-merlin-vertical-ledger":
        raise ValueError("unexpected vertical cohort ledger")
    hotspot_paths = load_year_map(args.hotspots)
    hotspot_manifest_paths = load_year_map(args.hotspot_manifest)
    years = {int(overpass["year"]) for overpass in vertical["overpasses"]}
    if set(hotspot_paths) != years or set(hotspot_manifest_paths) != years:
        raise ValueError("hotspot archives/manifests must exactly cover cohort years")

    crosswalk_payload = yaml.safe_load(args.fuel_crosswalk.read_text(encoding="utf-8"))
    crosswalk = {
        str(key).upper(): str(value).upper() for key, value in crosswalk_payload["rules"].items()
    }
    required_dates_by_year: dict[int, set[str]] = {year: set() for year in years}
    for overpass in vertical["overpasses"]:
        required_dates_by_year[int(overpass["year"])].update(
            str(value)[:10] for value in overpass["acquisition_times"]
        )
    hotspots_by_year = {}
    hotspot_sources = {}
    for year in sorted(years):
        hotspots_by_year[year], hotspot_sources[year] = load_hotspots(
            hotspot_paths[year],
            year=year,
            required_dates=required_dates_by_year[year],
        )
        manifest = json.loads(hotspot_manifest_paths[year].read_text(encoding="utf-8"))
        if manifest["file"]["sha256"] != hotspot_sources[year]["sha256"]:
            raise ValueError(f"Fire M3 {year} archive does not match its manifest")
        hotspot_sources[year]["acquisition_manifest"] = artifact(hotspot_manifest_paths[year])

    area_results = load_area_results(load_year_map(args.mcd64_area_results))
    transport_path = (
        args.transport_ledger.expanduser().resolve() if args.transport_ledger is not None else None
    )
    transport_results = load_transport_results(transport_path)
    assignments = []
    events_by_year: dict[int, dict[str, dict[str, Any]]] = {year: {} for year in years}
    for overpass in vertical["overpasses"]:
        overpass_id = str(overpass["overpass_id"])
        year = int(overpass["year"])
        selected = select_assignment(overpass, hotspots_by_year[year], crosswalk)
        if selected is None:
            assignments.append(
                {
                    "overpass_id": overpass_id,
                    "event_id": None,
                    "assignment_method": ASSIGNMENT_METHOD,
                    "status": "excluded_input_invalid",
                    "exclusion_reason": (
                        "no complete Fire M3 source within the frozen "
                        f"{MAXIMUM_DISTANCE_KM:g} km/{MAXIMUM_TIME_OFFSET_HOURS:g} h rule"
                    ),
                    "artifacts": {
                        "cffdrs_state": None,
                        "fuel": None,
                        "independent_area": None,
                        "transport_meteorology": None,
                    },
                }
            )
            continue

        row = selected["row"]
        group = selected["group"]
        event_id = fire_event_id(row)
        event_directory = output / overpass_id
        fire_assignment_path = event_directory / "fire-assignment.json"
        fuel_path = event_directory / "fuel.json"
        cffdrs_path = event_directory / "cffdrs-state.json"
        common_source = {
            "provider": "NRCan CWFIS Fire M3",
            "archive_sha256": hotspot_sources[year]["sha256"],
            "provider_row_sha256": provider_row_hash(row),
        }
        atomic_json(
            fire_assignment_path,
            {
                "schema_version": 1,
                "artifact_type": "w3-input-only-fire-assignment",
                "overpass_id": overpass_id,
                "event_id": event_id,
                "assignment_method": ASSIGNMENT_METHOD,
                "frozen_tolerances": {
                    "maximum_distance_km": MAXIMUM_DISTANCE_KM,
                    "maximum_time_offset_hours": MAXIMUM_TIME_OFFSET_HOURS,
                },
                "selected_source": {
                    "observed_at_utc": group["observed_at_utc"],
                    "latitude": group["latitude"],
                    "longitude": group["longitude"],
                    "plume_region_names": [str(item["p_name"]) for item in group["plumes"]],
                    "provider_observed_at_utc": parse_time(row["rep_date"] + "+00:00")
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "provider_latitude": float(row["lat"]),
                    "provider_longitude": float(row["lon"]),
                    "distance_km": selected["distance_km"],
                    "absolute_time_offset_hours": selected["time_offset_hours"],
                },
                "selection_firewall": {
                    "plume_height_accessed_by_builder": False,
                    "candidate_output_accessed_by_builder": False,
                    "fields_used": [
                        "MISR provider source location and time",
                        "Fire M3 location, time, fuel, FFMC, DMC, and DC completeness",
                    ],
                },
                "source": common_source,
            },
        )
        atomic_json(
            fuel_path,
            {
                "schema_version": 1,
                "artifact_type": "w3-input-only-fuel",
                "overpass_id": overpass_id,
                "event_id": event_id,
                "provider_fuel": row["fuel"].strip(),
                "model_fuel": selected["resolved_fuel"],
                "crosswalk": artifact(args.fuel_crosswalk),
                "source": common_source,
            },
        )
        atomic_json(
            cffdrs_path,
            {
                "schema_version": 1,
                "artifact_type": "w3-input-only-cffdrs-state",
                "overpass_id": overpass_id,
                "event_id": event_id,
                "observed_at_utc": parse_time(row["rep_date"] + "+00:00")
                .isoformat()
                .replace("+00:00", "Z"),
                "ffmc": float(row["ffmc"]),
                "dmc": float(row["dmc"]),
                "dc": float(row["dc"]),
                "source": common_source,
            },
        )
        detection = {
            "detection_id": event_id.removeprefix("w3-fire-"),
            "observed_at": parse_time(row["rep_date"] + "+00:00")
            .isoformat()
            .replace("+00:00", "Z"),
            "latitude": float(row["lat"]),
            "longitude": float(row["lon"]),
            "source": row["source"].strip(),
            "sensor": row["sensor"].strip(),
            "agency": row.get("agency", "").strip(),
            "ecozone": row.get("ecozone", "").strip(),
            "fuel": row["fuel"].strip(),
            "model_fuel": selected["resolved_fuel"],
            "ffmc": float(row["ffmc"]),
            "dmc": float(row["dmc"]),
            "dc": float(row["dc"]),
        }
        events_by_year[year].setdefault(
            event_id,
            {
                "event_id": event_id,
                "first_observed_at": detection["observed_at"],
                "last_observed_at": detection["observed_at"],
                "latitude": detection["latitude"],
                "longitude": detection["longitude"],
                "fuel_types": [selected["resolved_fuel"]],
                "maximum_estimated_area_ha": 0.0,
                "member_detection_ids": [detection["detection_id"]],
                "detections": [detection],
                "warnings": [],
            },
        )

        area_artifact = None
        status = "pending_input_only_assignment"
        exclusion_reason = None
        area_record = area_results.get(event_id)
        if area_record is not None:
            area_path = event_directory / "independent-area.json"
            atomic_json(
                area_path,
                {
                    "schema_version": 1,
                    "artifact_type": "w3-input-only-independent-area",
                    "overpass_id": overpass_id,
                    "event_id": event_id,
                    "operator_result": area_record["result"],
                    "source": area_record["source"],
                },
            )
            if area_record["result"]["burned_area_eligible"]:
                area_artifact = artifact(area_path)
            else:
                status = "excluded_input_invalid"
                exclusion_reason = (
                    "independent burned-area operator rejected the event: "
                    + ",".join(area_record["result"]["ineligibility_reasons"])
                )

        transport_artifact = None
        transport_record = transport_results.get(overpass_id)
        if transport_record is not None and transport_record.get("status") == "complete":
            transport_path_for_event = event_directory / "transport-meteorology.json"
            atomic_json(
                transport_path_for_event,
                {
                    "schema_version": 1,
                    "artifact_type": "w3-input-only-transport-meteorology",
                    "overpass_id": overpass_id,
                    "event_id": event_id,
                    "record": transport_record,
                    "source_ledger": artifact(transport_path),
                },
            )
            transport_artifact = artifact(transport_path_for_event)

        assignments.append(
            {
                "overpass_id": overpass_id,
                "event_id": event_id,
                "assignment_method": ASSIGNMENT_METHOD,
                "status": status,
                "exclusion_reason": exclusion_reason,
                "fire_assignment": artifact(fire_assignment_path),
                "artifacts": {
                    "cffdrs_state": artifact(cffdrs_path),
                    "fuel": artifact(fuel_path),
                    "independent_area": area_artifact,
                    "transport_meteorology": transport_artifact,
                },
            }
        )

    event_artifacts = {}
    for year, event_map in sorted(events_by_year.items()):
        events = list(event_map.values())
        path = output / f"input-only-events-{year}.json"
        atomic_json(
            path,
            {
                "schema_version": 1,
                "algorithm_version": ASSIGNMENT_METHOD,
                "event_count": len(events),
                "detection_count": len(events),
                "events": sorted(events, key=lambda item: item["event_id"]),
                "selection_firewall": {
                    "plume_height_used": False,
                    "candidate_output_used": False,
                },
            },
        )
        event_artifacts[str(year)] = artifact(path)

    assignment_payload = {
        "schema_version": 1,
        "artifact_type": "vertical-input-assignment-ledger",
        "selection_firewall": {
            "plume_height_used_for_assignment": False,
            "candidate_output_used_for_assignment": False,
            "allowed_evidence": [
                "source location and time",
                "provider fire records",
                "frozen fire geometry",
            ],
        },
        "complete_candidate_pool_preregistered": True,
        "complete_candidate_pool_rationale": (
            f"The complete supplied pool contains {len(vertical['overpasses'])} "
            "performance-blind MISR fire-overpass candidates. Source assignment uses "
            "only frozen observation identity, provider fire records, and input "
            "availability; no model result or model-observation agreement is permitted."
        ),
        "assignment_method": {
            "version": ASSIGNMENT_METHOD,
            "maximum_distance_km": MAXIMUM_DISTANCE_KM,
            "maximum_time_offset_hours": MAXIMUM_TIME_OFFSET_HOURS,
            "tie_break_order": [
                "distance",
                "absolute time offset",
                "MISR region name",
                "Fire M3 provider-row SHA-256",
            ],
        },
        "sources": {
            "vertical_ledger": artifact(vertical_path),
            "hotspots": {str(year): hotspot_sources[year] for year in sorted(years)},
            "fuel_crosswalk": artifact(args.fuel_crosswalk),
            "event_ledgers": event_artifacts,
        },
        "assignments": sorted(assignments, key=lambda item: item["overpass_id"]),
    }
    atomic_json(args.assignment_ledger.expanduser().resolve(), assignment_payload)
    summary = {
        "assignment_ledger": artifact(args.assignment_ledger.expanduser().resolve()),
        "assigned_count": sum(item["event_id"] is not None for item in assignments),
        "excluded_count": sum(item["status"] == "excluded_input_invalid" for item in assignments),
        "independent_area_complete_count": sum(
            item["artifacts"]["independent_area"] is not None for item in assignments
        ),
        "transport_complete_count": sum(
            item["artifacts"]["transport_meteorology"] is not None for item in assignments
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
