"""Prospective W6 one-factor-at-a-time sensitivity configuration builder."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def changed_json_paths(
    before: Any,
    after: Any,
    *,
    prefix: str = "",
) -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        paths = []
        for key in sorted(set(before) | set(after)):
            child = f"{prefix}/{key}"
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(changed_json_paths(before[key], after[key], prefix=child))
        return paths
    return [prefix or "/"] if before != after else []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_sensitivity_matrix(
    *,
    central_config: Path,
    matrix_specification: Path,
    output_directory: Path,
) -> dict[str, Any]:
    central = yaml.safe_load(central_config.read_text())
    specification = yaml.safe_load(matrix_specification.read_text())
    if specification.get("schema_version") != 1:
        raise ValueError("unsupported sensitivity matrix schema")
    output_directory.mkdir(parents=True, exist_ok=True)
    members = []
    identities = set()
    for member in specification["members"]:
        identity = member["candidate_id"]
        if identity in identities:
            raise ValueError(f"duplicate W6 candidate ID: {identity}")
        identities.add(identity)
        overrides = copy.deepcopy(member.get("overrides", {}))
        overrides["candidate_version"] = identity
        candidate = deep_merge(central, overrides)
        changes = changed_json_paths(central, candidate)
        declared = sorted(set(member["allowed_changed_paths"]) | {"/candidate_version"})
        if changes != declared:
            raise ValueError(f"{identity} changed paths {changes}, expected exactly {declared}")
        path = output_directory / f"{identity}.yaml"
        temporary = path.with_name(path.name + ".part")
        temporary.write_text(yaml.safe_dump(candidate, sort_keys=False))
        os.replace(temporary, path)
        members.append(
            {
                "candidate_id": identity,
                "factor": member["factor"],
                "level": member["level"],
                "path": path.as_posix(),
                "sha256": _sha256(path),
                "changed_json_paths": changes,
                "source_mass_group": member.get(
                    "source_mass_group",
                    "central-source-mass",
                ),
                "required": bool(member.get("required", True)),
            }
        )
    required_factors = {
        "central",
        "emission_factors",
        "burned_area",
        "vertical_injection",
        "particles",
        "threads",
        "deposition",
        "surface_background",
    }
    actual_factors = {member["factor"] for member in members if member["required"]}
    missing = sorted(required_factors - actual_factors)
    if missing:
        raise ValueError(f"W6 matrix lacks required factors: {missing}")
    manifest = {
        "schema_version": 1,
        "artifact_type": "frozen-smoke-sensitivity-matrix",
        "status": "frozen",
        "central_config": {
            "path": central_config.as_posix(),
            "sha256": _sha256(central_config),
        },
        "specification": {
            "path": matrix_specification.as_posix(),
            "sha256": _sha256(matrix_specification),
        },
        "member_count": len(members),
        "members": members,
    }
    manifest_path = output_directory / "matrix-manifest.json"
    temporary = manifest_path.with_name(manifest_path.name + ".part")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, manifest_path)
    return manifest


def evaluate_sensitivity_matrix(
    *,
    matrix_manifest: Path,
    result_manifests: list[Path],
    mass_absolute_tolerance_kg: float = 1e-9,
) -> dict[str, Any]:
    matrix = json.loads(matrix_manifest.read_text())
    expected = {item["candidate_id"]: item for item in matrix["members"]}
    results = {
        payload["candidate_id"]: (path, payload)
        for path in result_manifests
        for payload in [json.loads(path.read_text())]
    }
    unknown = sorted(set(results) - set(expected))
    if unknown:
        raise ValueError(f"results include candidates outside frozen matrix: {unknown}")
    records = []
    group_masses: dict[str, list[float]] = {}
    for candidate_id, member in expected.items():
        result_entry = results.get(candidate_id)
        if result_entry is None:
            records.append(
                {
                    "candidate_id": candidate_id,
                    "factor": member["factor"],
                    "level": member["level"],
                    "status": "missing",
                    "passed": False,
                }
            )
            continue
        path, result = result_entry
        verified = bool(result.get("whole_output_verified", False))
        source_mass = float(result["source_mass_kg"])
        group_masses.setdefault(member["source_mass_group"], []).append(source_mass)
        records.append(
            {
                "candidate_id": candidate_id,
                "factor": member["factor"],
                "level": member["level"],
                "status": "complete" if verified else "invalid",
                "passed": verified,
                "source_mass_kg": source_mass,
                "result_manifest_path": path.as_posix(),
                "result_manifest_sha256": _sha256(path),
                "scientific_metrics": result.get("scientific_metrics", {}),
                "engineering_checks": result.get("engineering_checks", {}),
            }
        )
    mass_checks = {}
    for group, masses in group_masses.items():
        spread = max(masses) - min(masses) if masses else 0.0
        mass_checks[group] = {
            "member_count": len(masses),
            "minimum_kg": min(masses) if masses else None,
            "maximum_kg": max(masses) if masses else None,
            "spread_kg": spread,
            "passed": spread <= mass_absolute_tolerance_kg,
        }
    record_lookup = {item["candidate_id"]: item for item in records}
    central_members = [item for item in expected.values() if item["factor"] == "central"]
    if len(central_members) != 1:
        raise ValueError("W6 matrix must contain exactly one central member")
    central = record_lookup[central_members[0]["candidate_id"]]
    central_metrics = central.get("scientific_metrics", {})
    reversals = []
    for record in records:
        if record["candidate_id"] == central["candidate_id"]:
            continue
        for workstream, metrics in record.get("scientific_metrics", {}).items():
            baseline = central_metrics.get(workstream, {})
            baseline_passed = baseline.get("criteria_passed")
            current_passed = metrics.get("criteria_passed")
            baseline_bias = baseline.get(
                "mean_bias",
                baseline.get("normalized_mean_bias"),
            )
            current_bias = metrics.get(
                "mean_bias",
                metrics.get("normalized_mean_bias"),
            )
            reasons = []
            if (
                isinstance(baseline_passed, bool)
                and isinstance(current_passed, bool)
                and baseline_passed != current_passed
            ):
                reasons.append("acceptance_pass_fail_changed")
            if (
                isinstance(baseline_bias, int | float)
                and isinstance(current_bias, int | float)
                and baseline_bias != 0
                and current_bias != 0
                and (baseline_bias < 0) != (current_bias < 0)
            ):
                reasons.append("bias_sign_changed")
            if baseline.get("event_ranking") != metrics.get("event_ranking") and (
                baseline.get("event_ranking") is not None
                or metrics.get("event_ranking") is not None
            ):
                reasons.append("event_ranking_changed")
            if reasons:
                reversals.append(
                    {
                        "candidate_id": record["candidate_id"],
                        "workstream": workstream,
                        "reasons": reasons,
                        "physical_explanation": None,
                        "independent_review_disposition": None,
                    }
                )
    emission_mass = {
        item["level"]: item.get("source_mass_kg")
        for item in records
        if item["factor"] == "emission_factors" and item["status"] == "complete"
    }
    central_mass = central.get("source_mass_kg")
    emission_mass_ordered = (
        isinstance(central_mass, int | float)
        and {"low", "high"} <= emission_mass.keys()
        and emission_mass["low"] < central_mass < emission_mass["high"]
    )
    return {
        "schema_version": 1,
        "artifact_type": "smoke-sensitivity-matrix-evaluation",
        "candidate_records": records,
        "mass_identity_checks": mass_checks,
        "all_required_candidates_valid": all(
            item["passed"] for item in records if expected[item["candidate_id"]]["required"]
        ),
        "all_mass_identity_checks_passed": all(item["passed"] for item in mass_checks.values()),
        "emission_factor_source_mass_ordered": emission_mass_ordered,
        "qualitative_reversals": reversals,
        "all_reversals_physically_explained_and_reviewed": (
            all(
                item["physical_explanation"] and item["independent_review_disposition"]
                for item in reversals
            )
            if reversals
            else True
        ),
    }
