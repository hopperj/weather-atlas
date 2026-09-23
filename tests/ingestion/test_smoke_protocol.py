import json
from pathlib import Path

import pytest
import yaml
from weather_ingest.smoke_protocol import (
    build_reviewed_release,
    freeze_successor_protocol,
)


def test_freeze_protocol_hashes_operators_before_output(tmp_path: Path) -> None:
    config = tmp_path / "protocol.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "status": "frozen",
                "protocol_id": "protocol-1",
                "holdout_output_opened": False,
            }
        )
    )
    document = tmp_path / "protocol.md"
    document.write_text("# Protocol\n")
    matrix = tmp_path / "matrix.yaml"
    matrix.write_text("schema_version: 1\n")
    operator = tmp_path / "operator.py"
    operator.write_text("VALUE = 1\n")
    output = tmp_path / "freeze.json"
    payload = freeze_successor_protocol(
        protocol_config=config,
        protocol_document=document,
        sensitivity_specification=matrix,
        operator_sources=[operator],
        output=output,
    )
    assert payload["status"] == "frozen"
    assert payload["holdout_output_opened"] is False
    assert len(payload["operator_sources"][0]["sha256"]) == 64


def test_reviewed_release_cannot_be_created_from_a_failing_gate(
    tmp_path: Path,
) -> None:
    release = tmp_path / "release.json"
    release.write_text(
        json.dumps(
            {
                "artifact_type": "cffeps-flexpart-corrected-model-release-freeze",
                "status": "frozen_pending_independent_review",
            }
        )
    )
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "artifact_type": "scientific-review-gate",
                "stage": "final",
                "passed": False,
            }
        )
    )
    with pytest.raises(ValueError, match="has not approved"):
        build_reviewed_release(
            release_freeze=release,
            final_review_gate=review,
            release_id="release-1",
            output=tmp_path / "reviewed.json",
        )
