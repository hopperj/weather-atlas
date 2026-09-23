"""Freeze the prospective protocol and corrected model release identities."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def _record(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def freeze_successor_protocol(
    *,
    protocol_config: Path,
    protocol_document: Path,
    sensitivity_specification: Path,
    operator_sources: list[Path],
    output: Path,
) -> dict[str, Any]:
    settings = yaml.safe_load(protocol_config.read_text())
    if settings.get("status") != "frozen" or settings.get("holdout_output_opened") is not False:
        raise ValueError("protocol must explicitly freeze before holdout output")
    payload = {
        "schema_version": 1,
        "artifact_type": "smoke-successor-protocol-freeze",
        "status": "frozen",
        "protocol_id": settings["protocol_id"],
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "holdout_output_opened": False,
        "protocol_config": _record(protocol_config),
        "protocol_document": _record(protocol_document),
        "sensitivity_specification": _record(sensitivity_specification),
        "operator_sources": [_record(path) for path in sorted(operator_sources)],
        "independent_pre_execution_review": "required_not_self_signed",
    }
    _write(output, payload)
    return payload


def freeze_model_release(
    *,
    w5_manifest: Path,
    executable_paths: list[Path],
    configuration_paths: list[Path],
    runner_paths: list[Path],
    extension_evidence_paths: list[Path] | None,
    output: Path,
) -> dict[str, Any]:
    w5 = json.loads(w5_manifest.read_text())
    if (
        w5.get("status") != "technical_complete_awaiting_independent_review"
        or w5.get("production_writes_enabled") is not False
    ):
        raise ValueError("W5 technical completion or production-write state is invalid")
    payload = {
        "schema_version": 1,
        "artifact_type": "cffeps-flexpart-corrected-model-release-freeze",
        "status": "frozen_pending_independent_review",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "w5_technical_completion": _record(w5_manifest),
        "executables": [_record(path) for path in sorted(executable_paths)],
        "configurations": [_record(path) for path in sorted(configuration_paths)],
        "runner_and_verifier_sources": [_record(path) for path in sorted(runner_paths)],
        "extension_evidence": [
            _record(path) for path in sorted(extension_evidence_paths or [])
        ],
        "production_writes_enabled": False,
        "independent_numerical_review": "required",
        "independent_emissions_science_review": "required",
    }
    _write(output, payload)
    return payload


def build_reviewed_release(
    *,
    release_freeze: Path,
    final_review_gate: Path,
    release_id: str,
    output: Path,
) -> dict[str, Any]:
    release = json.loads(release_freeze.read_text())
    review = json.loads(final_review_gate.read_text())
    if (
        release.get("artifact_type") != "cffeps-flexpart-corrected-model-release-freeze"
        or release.get("status") != "frozen_pending_independent_review"
    ):
        raise ValueError("corrected release is not in the reviewable frozen state")
    if (
        review.get("artifact_type") != "scientific-review-gate"
        or review.get("stage") != "final"
        or review.get("passed") is not True
    ):
        raise ValueError("final W7 review has not approved the frozen release")
    payload = {
        "schema_version": 1,
        "artifact_type": "cffeps-flexpart-reviewed-release",
        "status": "reviewed_frozen",
        "release_id": release_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "release_freeze": _record(release_freeze),
        "w7_final_review": {
            "passed": True,
            **_record(final_review_gate),
        },
        "production_writes_enabled": False,
    }
    _write(output, payload)
    return payload
