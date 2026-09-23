import json
from pathlib import Path

from weather_ingest.scientific_review import (
    build_review_package,
    validate_reviewer_signoffs,
)


def test_review_gate_requires_both_roles_and_matching_hashes(tmp_path: Path) -> None:
    artifact = tmp_path / "protocol.json"
    artifact.write_text('{"frozen":true}\n')
    package = tmp_path / "review"
    manifest = build_review_package(
        output_directory=package,
        artifacts=[artifact],
        protocol_id="protocol-1",
        candidate_id="candidate-1",
    )
    hashes = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    signoffs = []
    for index, role in enumerate(("emissions_plume_science", "air_quality_model_evaluation")):
        path = package / f"signoff-{index}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reviewer_id": f"reviewer-{index}",
                    "reviewer_role": role,
                    "name": f"Reviewer {index}",
                    "affiliation": "Independent institute",
                    "expertise": ["smoke modelling"],
                    "stage": "pre_execution",
                    "decision": "approve_for_prospective_execution",
                    "conflict_disclosure": "No conflicts.",
                    "access_limitations": "None.",
                    "attribution_and_publication_policy": "Acknowledgement requested.",
                    "comments": "Methods reviewed against the supplied artifacts.",
                    "signed_at_utc": "2026-07-26T12:00:00Z",
                    "signature_method": "reviewer-controlled attestation",
                    "artifact_hashes": hashes,
                }
            )
        )
        signoffs.append(path)
    report = validate_reviewer_signoffs(
        package_manifest=package / "source-and-build-manifest.json",
        issue_ledger=package / "issue-disposition-ledger.json",
        signoff_paths=signoffs,
        stage="pre_execution",
    )
    assert report["passed"]


def test_review_gate_does_not_self_approve_without_signoffs(tmp_path: Path) -> None:
    artifact = tmp_path / "protocol.json"
    artifact.write_text("{}")
    package = tmp_path / "review"
    build_review_package(
        output_directory=package,
        artifacts=[artifact],
        protocol_id="protocol-1",
        candidate_id="candidate-1",
    )
    report = validate_reviewer_signoffs(
        package_manifest=package / "source-and-build-manifest.json",
        issue_ledger=package / "issue-disposition-ledger.json",
        signoff_paths=[],
        stage="pre_execution",
    )
    assert not report["passed"]
