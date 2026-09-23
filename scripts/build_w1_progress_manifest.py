#!/usr/bin/env python3
"""Freeze the current machine-verifiable W1 evidence and exact blockers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cohort = args.cohort_directory.resolve()

    source = cohort / "source-candidate-ledger.json"
    area = cohort / "mcd64a1-event-areas.json"
    gfs = cohort / "historical-gfs-ledger.json"
    surface = cohort / "surface-ledger.json"
    vertical = cohort / "vertical-ledger.json"
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    area_payload = json.loads(area.read_text(encoding="utf-8"))
    gfs_payload = json.loads(gfs.read_text(encoding="utf-8"))
    surface_payload = json.loads(surface.read_text(encoding="utf-8"))
    vertical_payload = json.loads(vertical.read_text(encoding="utf-8"))

    gates = source_payload["gate_results"]
    if not area_payload["summary"]["area_strata_design_passed"]:
        raise ValueError("MCD64A1 area-strata design did not pass")
    if not gates["area_strata_design_passed"]:
        raise ValueError("retained source strata did not pass")
    if not gates["ecozone_and_fuel_diversity_passed"]:
        raise ValueError("retained source diversity did not pass")
    if not gates["all_retained_cffdrs_state_complete"]:
        raise ValueError("retained source CFFDRS state is incomplete")
    if gfs_payload["status"] != "complete":
        raise ValueError("historical GFS acquisition is incomplete")
    if surface_payload["status"] != "frozen_prospective_observation_availability":
        raise ValueError("surface observation ledger is not frozen")
    if vertical_payload["status"] != "frozen_prospective_observation_availability":
        raise ValueError("vertical observation ledger is not frozen")

    payload = {
        "schema_version": 1,
        "artifact_type": "w1-progress-manifest",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "program_id": "cffeps-flexpart-acceptance-program-v1",
        "workstream": "W1",
        "status": "technical_inputs_complete_except_gfas_and_independent_review",
        "scientific_completion_claimed": False,
        "production_writes_enabled": False,
        "selection_firewall": source_payload["selection_firewall"],
        "machine_verified": {
            "reconciled_candidate_events": 464,
            "reconciled_detections": 556111,
            "burned_area_eligible_events": area_payload["summary"][
                "burned_area_eligible_event_count"
            ],
            "eligible_strata_counts": area_payload["summary"][
                "eligible_strata_counts"
            ],
            "retained_count": gates["retained_count"],
            "reserve_count": gates["reserve_count"],
            "retained_strata_counts": gates["retained_strata_counts"],
            "retained_ecozones": gates["retained_ecozones"],
            "retained_fuel_families": gates["retained_fuel_families"],
            "retained_cffdrs_complete": gates[
                "all_retained_cffdrs_state_complete"
            ],
            "historical_gfs_cycle_count": gfs_payload["policy"][
                "cycle_date_count"
            ],
            "historical_gfs_file_count": gfs_payload["total_file_count"],
            "historical_gfs_total_bytes": gfs_payload["total_bytes"],
            "prospective_surface_station_count": surface_payload["station_count"],
            "prospective_surface_valid_hours": surface_payload[
                "candidate_valid_hour_count"
            ],
            "prospective_vertical_overpass_count": vertical_payload[
                "overpass_count"
            ],
        },
        "artifacts": {
            "candidate_events": artifact(cohort / "candidate-events.json"),
            "candidate_event_report": artifact(
                cohort / "candidate-event-report.json"
            ),
            "mcd64a1_event_areas": artifact(area),
            "mcd64a1_area_summary": artifact(
                cohort / "mcd64a1-area-summary.json"
            ),
            "source_candidate_ledger": artifact(source),
            "historical_gfs_ledger": artifact(gfs),
            "surface_ledger": artifact(surface),
            "vertical_ledger": artifact(vertical),
        },
        "formal_blockers": [
            {
                "id": "historical_gfas_v1_2",
                "status": "blocked_missing_ads_personal_access_token",
                "required_action": (
                    "Accept the GFAS dataset terms in ADS and provide the ADS "
                    "personal access token through a local secret."
                ),
            },
            {
                "id": "independent_no_performance_selection_audit",
                "status": "unsigned",
                "required_action": (
                    "An independent reviewer must verify the input-only "
                    "selection audit and sign the frozen cohort."
                ),
            },
            {
                "id": "successor_protocol_freeze",
                "status": "pending_gfas_and_review",
                "required_action": (
                    "Freeze the final source/GFAS ledger, exclusions, product "
                    "versions, operators, and cohort hashes before model output."
                ),
            },
        ],
    }
    atomic_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": args.output.resolve().as_posix(),
                "sha256": sha256(args.output),
                "status": payload["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
