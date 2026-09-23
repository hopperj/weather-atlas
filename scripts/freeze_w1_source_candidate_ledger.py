#!/usr/bin/env python3
"""Freeze a performance-blind W1 source-cohort candidate and reserve ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SELECTION_SEED = "cffeps-flexpart-w1-source-candidate-ledger-v1"
STRATA = ("weak", "moderate", "major")


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


def hash_rank(event_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}|{event_id}".encode()).hexdigest()


def fuel_family(code: str) -> str:
    family = "".join(character for character in code.upper() if character.isalpha())
    return family or code.upper()


def all_fire_weather_complete(event: dict[str, Any]) -> bool:
    return all(
        all(
            isinstance(detection.get(name), (int, float))
            and math.isfinite(float(detection[name]))
            for name in ("ffmc", "dmc", "dc")
        )
        for detection in event["detections"]
    )


def ledger_event(
    area: dict[str, Any],
    event: dict[str, Any],
    *,
    role: str,
    rank: int,
) -> dict[str, Any]:
    screening = event["input_only_screening"]
    source_dates = sorted(area["daily_area"]["central_daily_increment_ha"])
    return {
        "event_id": event["event_id"],
        "role": role,
        "deterministic_rank_within_stratum": rank,
        "area_stratum": area["area_stratum"],
        "central_area_ha": area["central_area_ha"],
        "high_confidence_area_ha": area["high_confidence_area_ha"],
        "central_daily_increment_ha": area["daily_area"][
            "central_daily_increment_ha"
        ],
        "positive_area_source_dates": source_dates,
        "first_observed_at": event["first_observed_at"],
        "last_observed_at": event["last_observed_at"],
        "latitude": event["latitude"],
        "longitude": event["longitude"],
        "member_detection_count": len(event["detections"]),
        "fuel_types": event["fuel_types"],
        "fuel_families": sorted({fuel_family(code) for code in event["fuel_types"]}),
        "ecozones": screening["ecozones"],
        "agencies": screening["agencies"],
        "source_perimeter_uids": screening["source_perimeter_uids"],
        "cffdrs_state_complete_for_all_detections": all_fire_weather_complete(event),
        "event_matching_warnings": event["warnings"],
        "mcd64a1_ambiguous_claim_pixel_count": area[
            "ambiguous_claim_pixel_count"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--event-report", type=Path, required=True)
    parser.add_argument("--areas", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retained-per-stratum", type=int, default=3)
    parser.add_argument("--reserve-per-stratum", type=int, default=2)
    args = parser.parse_args()
    if args.retained_per_stratum < 3 or args.reserve_per_stratum < 1:
        parser.error("retain at least three and reserve at least one per stratum")

    events_payload = json.loads(args.events.read_text(encoding="utf-8"))
    areas_payload = json.loads(args.areas.read_text(encoding="utf-8"))
    events = {item["event_id"]: item for item in events_payload["events"]}
    areas = {item["event_id"]: item for item in areas_payload["events"]}
    if set(events) != set(areas):
        raise ValueError("event and MCD64A1 area identities differ")

    eligible_by_stratum: dict[str, list[tuple[str, dict[str, Any]]]] = {
        name: [] for name in STRATA
    }
    exclusions: list[dict[str, Any]] = []
    for event_id, area in areas.items():
        event = events[event_id]
        reasons = list(area["ineligibility_reasons"])
        if not all_fire_weather_complete(event):
            reasons.append("incomplete_firem3_ffmc_dmc_dc")
        if not event["fuel_types"]:
            reasons.append("missing_supported_fbp_fuel")
        if not event["input_only_screening"]["ecozones"]:
            reasons.append("missing_firem3_ecozone")
        if reasons:
            exclusions.append(
                {
                    "event_id": event_id,
                    "reasons": sorted(set(reasons)),
                }
            )
            continue
        stratum = area["area_stratum"]
        if stratum not in eligible_by_stratum:
            raise ValueError(f"unexpected eligible area stratum: {stratum}")
        eligible_by_stratum[stratum].append((event_id, area))

    retained: list[dict[str, Any]] = []
    reserves: list[dict[str, Any]] = []
    not_sampled: list[dict[str, Any]] = []
    for stratum in STRATA:
        ranked = sorted(
            eligible_by_stratum[stratum],
            key=lambda item: (hash_rank(item[0]), item[0]),
        )
        required = args.retained_per_stratum + args.reserve_per_stratum
        if len(ranked) < required:
            raise ValueError(
                f"{stratum} has {len(ranked)} eligible events; {required} required"
            )
        for index, (event_id, area) in enumerate(ranked, start=1):
            event = events[event_id]
            if index <= args.retained_per_stratum:
                retained.append(
                    ledger_event(area, event, role="retained", rank=index)
                )
            elif index <= required:
                reserves.append(
                    ledger_event(area, event, role="reserve", rank=index)
                )
            else:
                not_sampled.append(
                    {
                        "event_id": event_id,
                        "area_stratum": stratum,
                        "reason": "not_selected_by_deterministic_stratified_rank",
                        "deterministic_rank_within_stratum": index,
                    }
                )

    retained_ecozones = sorted(
        {ecozone for item in retained for ecozone in item["ecozones"]}
    )
    retained_fuel_families = sorted(
        {family for item in retained for family in item["fuel_families"]}
    )
    retained_strata = Counter(item["area_stratum"] for item in retained)
    strata_passed = all(retained_strata[name] >= 3 for name in STRATA)
    diversity_passed = (
        len(retained_ecozones) >= 2 and len(retained_fuel_families) >= 2
    )
    if not strata_passed or not diversity_passed:
        raise ValueError(
            "deterministic retained cohort does not meet strata/ecozone/fuel targets"
        )
    acquisition_dates = sorted(
        {
            day
            for item in retained + reserves
            for day in item["positive_area_source_dates"]
        }
    )
    payload = {
        "schema_version": 1,
        "artifact_type": "w1-input-only-source-candidate-ledger",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "preliminary_frozen_pending_gfas_meteorology_and_review",
        "selection_seed": SELECTION_SEED,
        "selection_firewall": {
            "flexpart_output_accessed": False,
            "gfas_values_accessed": False,
            "plume_height_values_used": False,
            "surface_pm25_values_used": False,
            "model_performance_used": False,
            "selection_variables": [
                "QA-valid unambiguous MCD64A1 occurrence area",
                "Fire M3 fuel, ecozone, and FFMC/DMC/DC completeness",
                "deterministic SHA-256 rank within area stratum",
            ],
        },
        "sources": {
            "events": {
                "path": args.events.resolve().as_posix(),
                "sha256": sha256(args.events),
            },
            "event_report": {
                "path": args.event_report.resolve().as_posix(),
                "sha256": sha256(args.event_report),
            },
            "mcd64a1_event_areas": {
                "path": args.areas.resolve().as_posix(),
                "sha256": sha256(args.areas),
            },
            "builder": {
                "path": Path(__file__).resolve().as_posix(),
                "sha256": sha256(Path(__file__).resolve()),
            },
        },
        "design": {
            "retained_per_stratum": args.retained_per_stratum,
            "reserve_per_stratum": args.reserve_per_stratum,
            "minimum_ecozones": 2,
            "minimum_fuel_families": 2,
        },
        "gate_results": {
            "retained_count": len(retained),
            "reserve_count": len(reserves),
            "retained_strata_counts": {
                name: retained_strata[name] for name in STRATA
            },
            "retained_ecozones": retained_ecozones,
            "retained_fuel_families": retained_fuel_families,
            "area_strata_design_passed": strata_passed,
            "ecozone_and_fuel_diversity_passed": diversity_passed,
            "all_retained_cffdrs_state_complete": all(
                item["cffdrs_state_complete_for_all_detections"]
                for item in retained
            ),
            "gfas_complete": False,
            "historical_meteorology_complete": False,
            "independent_selection_audit_signed": False,
        },
        "required_acquisition_dates_retained_and_reserve": acquisition_dates,
        "retained_events": sorted(retained, key=lambda item: item["event_id"]),
        "reserve_events": sorted(reserves, key=lambda item: item["event_id"]),
        "exclusions": sorted(exclusions, key=lambda item: item["event_id"]),
        "eligible_not_sampled": sorted(
            not_sampled,
            key=lambda item: item["event_id"],
        ),
    }
    atomic_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": args.output.resolve().as_posix(),
                "sha256": sha256(args.output),
                **payload["gate_results"],
                "required_acquisition_date_count": len(acquisition_dates),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
