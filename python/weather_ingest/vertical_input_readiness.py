"""Input-only readiness audit for the prospective MISR vertical cohort."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_INPUT_CLASSES = {
    "fire_assignment",
    "fuel",
    "independent_area",
    "cffdrs_state",
    "transport_meteorology",
}


def _verify_artifact(record: dict[str, Any]) -> bool:
    path = Path(record["path"]).resolve()
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def build_assignment_template(vertical_ledger: dict[str, Any]) -> dict[str, Any]:
    return {
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
        "complete_candidate_pool_preregistered": vertical_ledger["overpass_count"] >= 20,
        "complete_candidate_pool_rationale": "",
        "assignments": [
            {
                "overpass_id": overpass["overpass_id"],
                "event_id": None,
                "assignment_method": None,
                "status": "pending_input_only_assignment",
                "exclusion_reason": None,
                "artifacts": {
                    name: None for name in sorted(REQUIRED_INPUT_CLASSES - {"fire_assignment"})
                },
            }
            for overpass in vertical_ledger["overpasses"]
        ],
    }


def audit_vertical_input_readiness(
    *,
    vertical_ledger_path: Path,
    assignment_ledger_path: Path,
    minimum_overpasses: int = 10,
) -> dict[str, Any]:
    vertical = json.loads(vertical_ledger_path.read_text())
    assignment = json.loads(assignment_ledger_path.read_text())
    if vertical.get("artifact_type") != "w1-input-only-misr-merlin-vertical-ledger":
        raise ValueError("unexpected prospective vertical ledger")
    if assignment["selection_firewall"] != {
        "plume_height_used_for_assignment": False,
        "candidate_output_used_for_assignment": False,
        "allowed_evidence": [
            "source location and time",
            "provider fire records",
            "frozen fire geometry",
        ],
    }:
        raise ValueError("vertical assignment firewall changed")
    expected = {item["overpass_id"] for item in vertical["overpasses"]}
    records = {item["overpass_id"]: item for item in assignment["assignments"]}
    if set(records) != expected:
        raise ValueError("assignment ledger does not exactly cover prospective overpasses")
    audited = []
    ready_count = 0
    excluded_count = 0
    for overpass_id in sorted(expected):
        record = records[overpass_id]
        if record["status"] == "excluded_input_invalid":
            if not record.get("exclusion_reason"):
                raise ValueError(f"input-only exclusion lacks reason: {overpass_id}")
            excluded_count += 1
            audited.append(
                {
                    "overpass_id": overpass_id,
                    "status": record["status"],
                    "missing_input_classes": [],
                }
            )
            continue
        missing = []
        if not record.get("event_id") or not record.get("assignment_method"):
            missing.append("fire_assignment")
        for input_class in sorted(REQUIRED_INPUT_CLASSES - {"fire_assignment"}):
            artifact = record.get("artifacts", {}).get(input_class)
            if not artifact or not _verify_artifact(artifact):
                missing.append(input_class)
        status = "ready" if not missing else "pending"
        ready_count += status == "ready"
        audited.append(
            {
                "overpass_id": overpass_id,
                "event_id": record.get("event_id"),
                "status": status,
                "missing_input_classes": missing,
            }
        )
    pool_preregistered = bool(
        assignment.get("complete_candidate_pool_preregistered")
        and assignment.get("complete_candidate_pool_rationale")
    )
    passed = ready_count >= minimum_overpasses and pool_preregistered
    return {
        "schema_version": 1,
        "artifact_type": "vertical-input-readiness-audit",
        "status": "passed" if passed else "blocked",
        "all_required_vertical_inputs_complete": passed,
        "minimum_overpasses": minimum_overpasses,
        "prospective_overpass_count": len(expected),
        "ready_overpass_count": ready_count,
        "excluded_input_invalid_count": excluded_count,
        "candidate_pool_preregistered": pool_preregistered,
        "records": audited,
        "vertical_ledger_sha256": hashlib.sha256(vertical_ledger_path.read_bytes()).hexdigest(),
        "assignment_ledger_sha256": hashlib.sha256(assignment_ledger_path.read_bytes()).hexdigest(),
    }
