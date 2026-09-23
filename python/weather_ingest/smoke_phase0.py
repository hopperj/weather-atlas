"""Phase-0 cohort finalization and execution-gate helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise FileNotFoundError(f"artifact is not a regular file: {resolved}")
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def verify_artifact_record(record: dict[str, Any]) -> Path:
    path = Path(str(record["path"])).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"recorded artifact is unavailable: {path}")
    if "size_bytes" in record and path.stat().st_size != int(record["size_bytes"]):
        raise ValueError(f"recorded artifact size changed: {path}")
    if sha256(path) != str(record["sha256"]):
        raise ValueError(f"recorded artifact checksum changed: {path}")
    return path


def finalize_w1_source_gfas(
    *,
    source_candidate_ledger_path: Path,
    gfas_manifest_path: Path,
    historical_gfs_ledger_path: Path,
    vertical_ledger_path: Path,
    surface_ledger_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = load_json(source_candidate_ledger_path)
    gfas = load_json(gfas_manifest_path)
    gfs = load_json(historical_gfs_ledger_path)
    vertical = load_json(vertical_ledger_path)
    surface = load_json(surface_ledger_path)
    if source.get("artifact_type") != "w1-input-only-source-candidate-ledger":
        raise ValueError("unexpected source candidate ledger")
    if gfas.get("artifact_type") != "cams-gfas-v1.2-ads-validation-archive":
        raise ValueError("unexpected GFAS archive manifest")
    if gfas.get("status") != "complete" or gfs.get("status") != "complete":
        raise ValueError("GFAS or historical meteorology is incomplete")
    if vertical.get("status") != "frozen_prospective_observation_availability":
        raise ValueError("vertical availability ledger is not frozen")
    if surface.get("status") != "frozen_prospective_observation_availability":
        raise ValueError("surface availability ledger is not frozen")

    required_dates = {
        str(value) for value in source["required_acquisition_dates_retained_and_reserve"]
    }
    gfas_dates = {str(value) for value in gfas["coverage"]["dates"]}
    if gfas_dates != required_dates:
        raise ValueError("GFAS dates do not exactly match the source cohort")
    if int(gfs["policy"]["source_date_count"]) != len(required_dates):
        raise ValueError("historical GFS source-date count does not match the cohort")
    gfs_source = gfs["source_candidate_ledger"]
    if Path(str(gfs_source["path"])).resolve() != source_candidate_ledger_path.resolve():
        raise ValueError("historical GFS ledger references a different source cohort")
    if str(gfs_source["sha256"]) != sha256(source_candidate_ledger_path):
        raise ValueError("historical GFS ledger references a changed source cohort")

    for record in gfas["files"]:
        verify_artifact_record(record["file"])
    for event in [*source["retained_events"], *source["reserve_events"]]:
        if not event["cffdrs_state_complete_for_all_detections"]:
            raise ValueError(f"event lacks complete CFFDRS state: {event['event_id']}")
        if not set(event["positive_area_source_dates"]).issubset(gfas_dates):
            raise ValueError(f"event lacks GFAS dates: {event['event_id']}")

    finalized = copy.deepcopy(source)
    finalized["artifact_type"] = "w1-input-only-source-gfas-ledger"
    finalized["created_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    finalized["status"] = "technical_inputs_complete_pending_independent_review"
    finalized["parent_source_candidate_ledger"] = artifact(source_candidate_ledger_path)
    finalized["sources"]["gfas_v1_2"] = artifact(gfas_manifest_path)
    finalized["sources"]["historical_gfs"] = artifact(historical_gfs_ledger_path)
    finalized["gate_results"]["gfas_complete"] = True
    finalized["gate_results"]["historical_meteorology_complete"] = True
    finalized["gate_results"]["independent_selection_audit_signed"] = False
    finalized["selection_firewall"].pop("gfas_values_accessed", None)
    finalized["selection_firewall"].update(
        {
            "gfas_values_accessed_by_event_selector": False,
            "gfas_values_accessed_by_integrity_validator": True,
            "gfas_magnitudes_used_for_selection": False,
        }
    )
    for event in [*finalized["retained_events"], *finalized["reserve_events"]]:
        event["input_completeness"] = {
            "independent_area": bool(float(event["central_area_ha"]) > 0),
            "fuel": bool(event["fuel_families"]),
            "cffdrs": bool(event["cffdrs_state_complete_for_all_detections"]),
            "gfas": set(event["positive_area_source_dates"]).issubset(gfas_dates),
            "meteorology": True,
        }
        event["all_required_source_inputs_complete"] = all(event["input_completeness"].values())

    all_events_complete = all(
        event["all_required_source_inputs_complete"]
        for event in [*finalized["retained_events"], *finalized["reserve_events"]]
    )
    completeness = {
        "artifact_type": "w1-source-input-completeness",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "passed" if all_events_complete else "failed",
        "date_count": len(required_dates),
        "retained_event_count": len(finalized["retained_events"]),
        "reserve_event_count": len(finalized["reserve_events"]),
        "all_required_source_inputs_complete": all_events_complete,
        "checks": {
            "independent_area_complete": all(
                event["input_completeness"]["independent_area"]
                for event in [*finalized["retained_events"], *finalized["reserve_events"]]
            ),
            "fuel_complete": all(
                event["input_completeness"]["fuel"]
                for event in [*finalized["retained_events"], *finalized["reserve_events"]]
            ),
            "cffdrs_complete": all(
                event["input_completeness"]["cffdrs"]
                for event in [*finalized["retained_events"], *finalized["reserve_events"]]
            ),
            "gfas_complete": gfas_dates == required_dates,
            "meteorology_complete": True,
        },
        "inputs": {
            "source_candidate_ledger": artifact(source_candidate_ledger_path),
            "gfas_manifest": artifact(gfas_manifest_path),
            "historical_gfs_ledger": artifact(historical_gfs_ledger_path),
        },
    }
    if not all_events_complete:
        raise ValueError("one or more W1 source events has incomplete technical inputs")

    cohort_freeze = {
        "artifact_type": "w1-technical-cohort-freeze",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "technical_complete_pending_independent_review",
        "cohort_id": source_candidate_ledger_path.resolve().parent.name,
        "technical_inputs_complete": True,
        "independent_no_performance_selection_review_signed": False,
        "holdout_output_opened": False,
        "artifacts": {
            "source_candidate_ledger": artifact(source_candidate_ledger_path),
            "gfas_manifest": artifact(gfas_manifest_path),
            "historical_gfs_ledger": artifact(historical_gfs_ledger_path),
            "vertical_ledger": artifact(vertical_ledger_path),
            "surface_ledger": artifact(surface_ledger_path),
        },
        "selection_firewall": {
            "candidate_output_accessed": False,
            "model_performance_used": False,
            "observed_or_reference_magnitudes_used_for_selection": False,
        },
    }
    return finalized, completeness, cohort_freeze


def phase0_preflight(
    *,
    cohort_freeze_path: Path | None,
    model_release_path: Path | None,
    protocol_freeze_path: Path | None,
    sensitivity_matrix_freeze_path: Path | None,
    reviewer_approval_path: Path | None,
    holdout_output_opened: bool,
    vertical_input_readiness_path: Path | None = None,
) -> dict[str, Any]:
    def load_optional(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if path is None or not path.is_file():
            return None, None
        return load_json(path), artifact(path)

    cohort, cohort_record = load_optional(cohort_freeze_path)
    release, release_record = load_optional(model_release_path)
    protocol, protocol_record = load_optional(protocol_freeze_path)
    matrix, matrix_record = load_optional(sensitivity_matrix_freeze_path)
    review, review_record = load_optional(reviewer_approval_path)
    vertical, vertical_record = load_optional(vertical_input_readiness_path)
    checks = {
        "all_required_inputs_complete": bool(
            cohort
            and cohort.get("technical_inputs_complete") is True
            and vertical
            and vertical.get("all_required_vertical_inputs_complete") is True
        ),
        "vertical_inputs_complete": bool(
            vertical and vertical.get("all_required_vertical_inputs_complete") is True
        ),
        "cohorts_frozen": bool(
            cohort
            and cohort.get("status")
            in {
                "technical_complete_pending_independent_review",
                "complete_independently_reviewed",
            }
        ),
        "model_release_frozen": bool(
            release
            and release.get("status")
            in {"frozen", "frozen_pending_independent_review", "reviewed_frozen"}
        ),
        "operators_and_thresholds_frozen": bool(protocol and protocol.get("status") == "frozen"),
        "sensitivity_matrix_frozen": bool(matrix and matrix.get("status") == "frozen"),
        "reviewer_approval_to_execute": bool(
            review
            and (
                (
                    review.get("status") in {"approved", "approved_with_non_blocking_comments"}
                    and int(review.get("open_blocking_comment_count", -1)) == 0
                )
                or (
                    review.get("artifact_type") == "scientific-review-gate"
                    and review.get("stage") == "pre_execution"
                    and review.get("passed") is True
                )
            )
        ),
        "holdout_output_opened_before_freeze": bool(holdout_output_opened),
    }
    passed = (
        all(value for key, value in checks.items() if key != "holdout_output_opened_before_freeze")
        and not checks["holdout_output_opened_before_freeze"]
    )
    return {
        "artifact_type": "smoke-phase0-execution-preflight",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "passed" if passed else "blocked",
        "holdout_execution_authorized": passed,
        "checks": checks,
        "artifacts": {
            "cohort_freeze": cohort_record,
            "model_release": release_record,
            "protocol_freeze": protocol_record,
            "sensitivity_matrix_freeze": matrix_record,
            "reviewer_approval": review_record,
            "vertical_input_readiness": vertical_record,
        },
    }
