"""Artifact-specific independent scientific review package and gate checks."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REQUIRED_REVIEWER_ROLES = {
    "emissions_plume_science",
    "air_quality_model_evaluation",
}
PRE_EXECUTION_DECISIONS = {
    "approve_for_prospective_execution",
    "approve_with_non_blocking_comments",
    "revise_before_execution",
}
FINAL_DECISIONS = {
    "approved",
    "approved_with_non_blocking_limitations",
    "rejected",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_review_package(
    *,
    output_directory: Path,
    artifacts: list[Path],
    protocol_id: str,
    candidate_id: str,
) -> dict[str, Any]:
    if not artifacts:
        raise ValueError("review package requires at least one frozen artifact")
    records = []
    for path in sorted(set(artifacts)):
        if not path.is_file():
            raise FileNotFoundError(path)
        records.append(
            {
                "path": path.resolve().as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    package = {
        "schema_version": 1,
        "artifact_type": "independent-scientific-review-package",
        "protocol_id": protocol_id,
        "candidate_id": candidate_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "required_reviewer_roles": sorted(REQUIRED_REVIEWER_ROLES),
        "artifacts": records,
    }
    manifest_path = output_directory / "source-and-build-manifest.json"
    temporary = manifest_path.with_name(manifest_path.name + ".part")
    temporary.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, manifest_path)
    issue_path = output_directory / "issue-disposition-ledger.json"
    if not issue_path.exists():
        issue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_type": "scientific-review-issue-ledger",
                    "issues": [],
                },
                indent=2,
            )
            + "\n"
        )
    signoff_directory = output_directory / "reviewer-signoffs"
    signoff_directory.mkdir(exist_ok=True)
    signoff_template = signoff_directory / "reviewer-signoff-template.json"
    if not signoff_template.exists():
        signoff_template.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reviewer_id": "reviewer-controlled-identifier",
                    "reviewer_role": (
                        "emissions_plume_science OR air_quality_model_evaluation"
                    ),
                    "name": "human reviewer name",
                    "affiliation": "reviewer affiliation",
                    "expertise": ["relevant expertise"],
                    "conflict_disclosure": "Specific disclosure, including none if none",
                    "access_limitations": "Specific limitations, including none if none",
                    "attribution_and_publication_policy": (
                        "Authorship, acknowledgement, and publication expectations"
                    ),
                    "stage": "pre_execution OR final",
                    "decision": "Use a decision allowed for the selected stage",
                    "comments": "Reviewer-authored rationale and limitations",
                    "artifact_hashes": {
                        "/absolute/path/from-source-and-build-manifest": "exact sha256"
                    },
                    "signed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
                    "signature_method": "Reviewer-controlled attestation method",
                },
                indent=2,
            )
            + "\n"
        )
    for name in (
        "protocol",
        "cohort-ledgers",
        "methods",
        "evaluation-reports",
        "sensitivity-reports",
        "failed-attempt-ledger",
    ):
        (output_directory / name).mkdir(exist_ok=True)
    evidence_path = output_directory / "acceptance-evidence-matrix.yaml"
    if not evidence_path.exists():
        evidence_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "protocol_id": protocol_id,
                    "candidate_id": candidate_id,
                    "gates": {
                        name: {
                            "status": "pending",
                            "evidence_artifact_sha256": None,
                            "reviewer_disposition": None,
                        }
                        for name in (
                            "phase0_prospective_freeze",
                            "w2_gfas_source",
                            "w3_vertical_plume",
                            "w4_surface_pm25",
                            "w5_numerical_correction",
                            "w6_sensitivity",
                            "w7_independent_review",
                            "w8_shadow_cycles",
                        )
                    },
                },
                sort_keys=False,
            )
        )
    reproduction_path = output_directory / "reproduction-commands.md"
    if not reproduction_path.exists():
        reproduction_path.write_text(
            "# Reproduction commands\n\n"
            "Commands must be copied from immutable manifests after each stage. "
            "Credentials are referenced by environment-variable name and must never "
            "be embedded here. Start with `scripts/build_smoke_phase0_preflight.py`; "
            "do not execute held-out candidates until that artifact authorizes them.\n"
        )
    claims_path = output_directory / "permitted-and-prohibited-claims.md"
    if not claims_path.exists():
        claims_path.write_text(
            "# Permitted and prohibited claims\n\n"
            "Permitted: report frozen-cohort results, uncertainty, failures, "
            "limitations, and artifact-specific reviewer decisions.\n\n"
            "Prohibited: claim scientific acceptance before every gate passes; "
            "replace a failed central experiment with a sensitivity; generalize "
            "beyond the evaluated domain, period, species, products, or operators; "
            "or infer authorization to enable production writes.\n"
        )
    readme_path = output_directory / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "# Independent scientific review package\n\n"
            "This package is evidence for review, not a self-approval. Reviewers must "
            "write their own artifact-specific JSON signoffs into `reviewer-signoffs/`. "
            "The software verifies hashes, roles, conflicts, decisions, and blocking "
            "issues; it never creates a passing signoff.\n"
        )
    return package


def validate_issue_ledger(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    identities = set()
    blocking_open = []
    for issue in payload["issues"]:
        identity = issue["issue_id"]
        if identity in identities:
            raise ValueError(f"duplicate scientific review issue: {identity}")
        identities.add(identity)
        if issue["severity"] not in {"blocking", "non_blocking"}:
            raise ValueError(f"invalid issue severity: {identity}")
        if issue["status"] not in {"open", "resolved", "withdrawn"}:
            raise ValueError(f"invalid issue status: {identity}")
        if issue["severity"] == "blocking" and issue["status"] == "open":
            blocking_open.append(identity)
        if issue["status"] == "resolved" and not all(
            issue.get(field)
            for field in ("response_sha256", "reviewer_disposition", "closed_at_utc")
        ):
            raise ValueError(f"resolved issue lacks closure evidence: {identity}")
    return {
        "issue_count": len(identities),
        "open_blocking_issue_ids": sorted(blocking_open),
        "zero_open_blocking_issues": not blocking_open,
    }


def validate_reviewer_signoffs(
    *,
    package_manifest: Path,
    issue_ledger: Path,
    signoff_paths: list[Path],
    stage: str,
) -> dict[str, Any]:
    if stage not in {"pre_execution", "final"}:
        raise ValueError("review stage must be pre_execution or final")
    package = json.loads(package_manifest.read_text())
    expected_artifacts = {item["path"]: item["sha256"] for item in package["artifacts"]}
    decisions = PRE_EXECUTION_DECISIONS if stage == "pre_execution" else FINAL_DECISIONS
    records = []
    roles = set()
    reviewer_ids = set()
    for path in signoff_paths:
        signoff = json.loads(path.read_text())
        if signoff.get("schema_version") != 1:
            raise ValueError(f"unsupported reviewer signoff schema in {path}")
        reviewer_id = signoff["reviewer_id"]
        role = signoff["reviewer_role"]
        if reviewer_id in reviewer_ids:
            raise ValueError(f"reviewer signs more than once: {reviewer_id}")
        reviewer_ids.add(reviewer_id)
        if role not in REQUIRED_REVIEWER_ROLES:
            raise ValueError(f"unqualified reviewer role in {path}: {role}")
        roles.add(role)
        if signoff["stage"] != stage or signoff["decision"] not in decisions:
            raise ValueError(f"invalid stage or decision in {path}")
        if not signoff.get("conflict_disclosure"):
            raise ValueError(f"missing conflict disclosure in {path}")
        required_reviewer_metadata = (
            "name",
            "affiliation",
            "expertise",
            "comments",
            "access_limitations",
            "attribution_and_publication_policy",
            "signed_at_utc",
            "signature_method",
        )
        if any(not signoff.get(field) for field in required_reviewer_metadata):
            raise ValueError(f"incomplete reviewer identity or attestation in {path}")
        if not isinstance(signoff["expertise"], list) or not all(
            isinstance(value, str) and value.strip() for value in signoff["expertise"]
        ):
            raise ValueError(f"reviewer expertise must be a non-empty string list in {path}")
        signed_at = datetime.fromisoformat(
            str(signoff["signed_at_utc"]).replace("Z", "+00:00")
        )
        if signed_at.tzinfo is None:
            raise ValueError(f"reviewer signoff timestamp is not timezone-aware in {path}")
        if signoff.get("artifact_hashes") != expected_artifacts:
            raise ValueError(f"artifact hashes do not match review package in {path}")
        records.append(
            {
                "reviewer_id": reviewer_id,
                "reviewer_role": role,
                "name": signoff["name"],
                "affiliation": signoff["affiliation"],
                "expertise": signoff["expertise"],
                "conflict_disclosure": signoff["conflict_disclosure"],
                "access_limitations": signoff["access_limitations"],
                "attribution_and_publication_policy": signoff[
                    "attribution_and_publication_policy"
                ],
                "decision": signoff["decision"],
                "signed_at_utc": signoff["signed_at_utc"],
                "signature_method": signoff["signature_method"],
                "signoff_path": path.as_posix(),
                "signoff_sha256": sha256(path),
            }
        )
    issues = validate_issue_ledger(issue_ledger)
    favourable = (
        {
            "approve_for_prospective_execution",
            "approve_with_non_blocking_comments",
        }
        if stage == "pre_execution"
        else {"approved", "approved_with_non_blocking_limitations"}
    )
    all_roles_present = roles >= REQUIRED_REVIEWER_ROLES
    all_decisions_favourable = len(records) >= 2 and all(
        record["decision"] in favourable for record in records
    )
    return {
        "schema_version": 1,
        "artifact_type": "scientific-review-gate",
        "stage": stage,
        "reviewers": records,
        "required_roles_present": all_roles_present,
        "all_decisions_favourable": all_decisions_favourable,
        **issues,
        "passed": (
            all_roles_present and all_decisions_favourable and issues["zero_open_blocking_issues"]
        ),
    }
