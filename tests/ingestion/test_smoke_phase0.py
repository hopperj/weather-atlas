from __future__ import annotations

import json
from pathlib import Path

from weather_ingest.smoke_phase0 import (
    phase0_preflight,
    sha256,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_phase0_preflight_blocks_missing_human_and_scientific_freezes(
    tmp_path: Path,
) -> None:
    cohort = _write(
        tmp_path / "cohort.json",
        {
            "technical_inputs_complete": True,
            "status": "technical_complete_pending_independent_review",
        },
    )
    vertical = _write(
        tmp_path / "vertical-readiness.json",
        {"all_required_vertical_inputs_complete": True},
    )
    report = phase0_preflight(
        cohort_freeze_path=cohort,
        model_release_path=None,
        protocol_freeze_path=None,
        sensitivity_matrix_freeze_path=None,
        reviewer_approval_path=None,
        holdout_output_opened=False,
        vertical_input_readiness_path=vertical,
    )
    assert report["status"] == "blocked"
    assert report["checks"]["all_required_inputs_complete"]
    assert not report["checks"]["reviewer_approval_to_execute"]


def test_phase0_preflight_passes_only_complete_signed_gate(tmp_path: Path) -> None:
    cohort = _write(
        tmp_path / "cohort.json",
        {
            "technical_inputs_complete": True,
            "status": "complete_independently_reviewed",
        },
    )
    release = _write(tmp_path / "release.json", {"status": "reviewed_frozen"})
    protocol = _write(tmp_path / "protocol.json", {"status": "frozen"})
    matrix = _write(tmp_path / "matrix.json", {"status": "frozen"})
    review = _write(
        tmp_path / "review.json",
        {"status": "approved", "open_blocking_comment_count": 0},
    )
    vertical = _write(
        tmp_path / "vertical-readiness.json",
        {"all_required_vertical_inputs_complete": True},
    )
    report = phase0_preflight(
        cohort_freeze_path=cohort,
        model_release_path=release,
        protocol_freeze_path=protocol,
        sensitivity_matrix_freeze_path=matrix,
        reviewer_approval_path=review,
        holdout_output_opened=False,
        vertical_input_readiness_path=vertical,
    )
    assert report["status"] == "passed"
    assert report["holdout_execution_authorized"]
    assert report["artifacts"]["model_release"]["sha256"] == sha256(release)


def test_phase0_preflight_never_passes_after_early_holdout_access(
    tmp_path: Path,
) -> None:
    files = {
        name: _write(tmp_path / f"{name}.json", payload)
        for name, payload in {
            "cohort": {
                "technical_inputs_complete": True,
                "status": "complete_independently_reviewed",
            },
            "release": {"status": "reviewed_frozen"},
            "protocol": {"status": "frozen"},
            "matrix": {"status": "frozen"},
            "review": {"status": "approved", "open_blocking_comment_count": 0},
            "vertical": {"all_required_vertical_inputs_complete": True},
        }.items()
    }
    report = phase0_preflight(
        cohort_freeze_path=files["cohort"],
        model_release_path=files["release"],
        protocol_freeze_path=files["protocol"],
        sensitivity_matrix_freeze_path=files["matrix"],
        reviewer_approval_path=files["review"],
        holdout_output_opened=True,
        vertical_input_readiness_path=files["vertical"],
    )
    assert report["status"] == "blocked"
    assert not report["holdout_execution_authorized"]
