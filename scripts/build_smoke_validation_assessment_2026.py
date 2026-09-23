#!/usr/bin/env python3
"""Build the machine-readable March--May 2026 smoke-validation assessment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CENTRAL_RELATIVE_PATH = Path(
    "candidates/march-may-2026-mcd64a1-central-v4/attempt-001"
)
AREA_RELATIVE_PATH = Path(
    "mcd64a1/mcd64a1-event-area-v2/mcd64a1-area-summary.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _evaluation_record(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    return {
        "artifact": _artifact(path),
        "assessment_role": payload["assessment_role"],
        "acceptance_capable": payload["acceptance_capable"],
        "passed": payload["passed"],
        "metrics": payload["metrics"],
        "criteria": payload["criteria"],
    }


def build_assessment(
    *,
    experiment_root: Path,
    repository_root: Path,
    generated_at: str,
) -> dict[str, Any]:
    experiment_root = experiment_root.resolve()
    repository_root = repository_root.resolve()
    central = experiment_root / CENTRAL_RELATIVE_PATH

    manifest_path = central / "manifest.json"
    input_manifest_path = central / "input-manifest.json"
    emissions_manifest_path = central / "input/emissions.manifest.json"
    verifier_path = (
        central / "verification/candidate-output-verification-v2.json"
    )
    balance_path = central / "verification/cffeps-finite-window-balance.json"
    area_path = experiment_root / AREA_RELATIVE_PATH
    sensitivity_path = (
        central / "evaluation/sensitivities/field-comparison.json"
    )
    aqs_path = central / "evaluation/aqs/manifest.json"

    manifest = _read_json(manifest_path)
    input_manifest = _read_json(input_manifest_path)
    emissions_manifest = _read_json(emissions_manifest_path)
    verifier = _read_json(verifier_path)
    balance = _read_json(balance_path)
    area = _read_json(area_path)
    sensitivities = _read_json(sensitivity_path)
    aqs = _read_json(aqs_path)

    if manifest.get("status") != "complete":
        raise ValueError("central candidate is not complete")
    if verifier.get("status") != "passed":
        raise ValueError("central candidate output verification did not pass")
    if area["summary"]["area_strata_design_passed"]:
        raise ValueError("expected the frozen area-strata design to have failed")
    if input_manifest["event_count"] != 5:
        raise ValueError("expected five retained central events")
    if not all(day["hard_gate_passed"] for day in balance["source_days"]):
        raise ValueError("one or more CFFEPS finite-window hard gates failed")

    evaluations = {
        "gfas_pm25": _evaluation_record(
            central
            / "evaluation/gfas/pairs/gfas-v1.4.2-pm25-evaluation.json"
        ),
        "gfas_co": _evaluation_record(
            central / "evaluation/gfas/pairs/gfas-v1.4.2-co-evaluation.json"
        ),
        "gfas_bc": _evaluation_record(
            central / "evaluation/gfas/pairs/gfas-v1.4.2-bc-evaluation.json"
        ),
        "tropomi_aerosol_mid_height": _evaluation_record(
            central / "evaluation/tropomi/evaluation.json"
        ),
        "airnow_pm25_median_background": _evaluation_record(
            central / "evaluation/airnow/median-evaluation.json"
        ),
        "airnow_pm25_p20_background": _evaluation_record(
            central / "evaluation/airnow/p20-evaluation.json"
        ),
    }
    if any(record["passed"] for record in evaluations.values()):
        raise ValueError("expected every completed external evaluation to fail")
    if aqs["central_pairs"]["pair_count"] != 0:
        raise ValueError("expected the frozen AQS operator to produce zero pairs")

    sensitivity_summary: dict[str, Any] = {}
    for label, comparison in sensitivities["comparisons"].items():
        sensitivity_summary[label] = {
            "candidate": comparison["candidate"],
            "verification": comparison["verification"],
            "whole_output_verification_passed": comparison[
                "whole_output_verification_passed"
            ],
            "source_mass_equal_to_central": comparison[
                "source_mass_equal_to_central"
            ],
            "source_mass_ratio_to_central": comparison[
                "source_mass_ratio_to_central"
            ],
            "concentration": comparison["fields"]["concentration"],
            "wet_deposition_status": comparison["fields"]["wet_deposition"][
                "status"
            ],
            "wet_deposition_nonfinite_count": comparison["fields"][
                "wet_deposition"
            ]["candidate_nonfinite_count"],
        }
    threads = sensitivity_summary["threads_1"]
    if (
        threads["whole_output_verification_passed"]
        or threads["wet_deposition_nonfinite_count"] != 2
    ):
        raise ValueError("one-thread sensitivity does not have its expected failure")

    protocol_names = [
        "smoke-validation-protocol-2026.md",
        "smoke-validation-protocol-2026-v2-amendment.md",
        "smoke-validation-protocol-2026-v3-amendment.md",
        "smoke-validation-protocol-2026-v4-amendment.md",
        "smoke-validation-protocol-2026-v5-amendment.md",
        "smoke-validation-protocol-2026-v6-sensitivities.md",
    ]
    protocol_chain = [
        _artifact(repository_root / "docs" / name) for name in protocol_names
    ]
    software_verification_path = (
        repository_root
        / "docs/smoke-validation-software-verification-2026-07-24.json"
    )
    software_verification = _read_json(software_verification_path)
    if software_verification.get("status") != "passed_with_declared_skips":
        raise ValueError("final software verification is not in its expected state")

    gate_assessment = [
        {
            "gate": "central_engineering_and_mass_integrity",
            "status": "passed",
            "acceptance_blocking": False,
            "evidence": (
                "24/24 FLEXPART members passed the schema-v2 independent "
                "whole-output verifier; all eight CFFEPS finite-window hard "
                "balance gates passed."
            ),
        },
        {
            "gate": "weak_moderate_major_population_design",
            "status": "failed",
            "acceptance_blocking": True,
            "evidence": (
                "MCD64A1 produced four weak, two moderate, and zero major "
                "area-qualified events; one moderate event was then excluded "
                "for missing required CWFIS FFMC, leaving five events."
            ),
        },
        {
            "gate": "gfas_gross_source_discrepancy",
            "status": "failed",
            "acceptance_blocking": True,
            "evidence": (
                "PM2.5, CO, and BC each failed the frozen NMB, correlation, "
                "and FAC2 diagnostic criteria. Unequal fire coverage is a "
                "known dominant confounder and remains unresolved."
            ),
        },
        {
            "gate": "acceptance_capable_vertical_profile_observation",
            "status": "not_run",
            "acceptance_blocking": True,
            "evidence": (
                "The completed TROPOMI comparison is diagnostic only and "
                "failed its RMSE criterion; no frozen MISR or lidar "
                "acceptance-capable matchup exists."
            ),
        },
        {
            "gate": "final_acceptance_capable_surface_pm25",
            "status": "not_run",
            "acceptance_blocking": True,
            "evidence": (
                "AirNow produced 14 provisional pairs and failed all central "
                "criteria; current-year AQS produced zero pairs. No final NAPS "
                "or equivalent frozen archive has been evaluated."
            ),
        },
        {
            "gate": "frozen_sensitivity_matrix",
            "status": "failed",
            "acceptance_blocking": True,
            "evidence": (
                "Low/high emission factors, high-confidence area, alternate "
                "injection, doubled particles, and one thread ran. The "
                "one-thread candidate contains two non-finite wet-deposition "
                "values, and a preregistered no-deposition causal run remains "
                "for a future amendment."
            ),
        },
        {
            "gate": "independent_scientific_review",
            "status": "pending",
            "acceptance_blocking": True,
            "evidence": (
                "Wildfire-emissions and air-quality scientific reviews are "
                "not signed."
            ),
        },
        {
            "gate": "four_scheduled_cycle_demonstrations",
            "status": "not_run",
            "acceptance_blocking": True,
            "evidence": "Only this frozen central validation cycle is complete.",
        },
    ]
    acceptance_blockers = [
        record["gate"]
        for record in gate_assessment
        if record["acceptance_blocking"] and record["status"] != "passed"
    ]

    return {
        "schema_version": 2,
        "assessment_id": "cffeps-flexpart-scientific-acceptance-2026-07-24-v2",
        "generated_at": generated_at,
        "experiment": {
            "id": "gfas-v1.4.2-2026-03-19_2026-05-31",
            "root": experiment_root.as_posix(),
            "candidate": manifest["candidate_version"],
            "candidate_status": manifest["status"],
            "candidate_created_at": manifest["created_at"],
            "candidate_wall_time_seconds": manifest["wall_time_seconds"],
            "event_count": input_manifest["event_count"],
            "event_day_count": input_manifest["event_day_count"],
            "source_days": input_manifest["source_days"],
            "transport_member_count": verifier["member_count"],
            "particle_count": verifier["particle_count"],
            "release_count": verifier["release_count"],
            "released_mass_kg_by_species": verifier[
                "release_mass_kg_by_species"
            ],
        },
        "decision": {
            "scientific_acceptance_status": "not_accepted",
            "production_submission_unlock_authorized": False,
            "simulation_writes_lock_should_remain_enabled": True,
            "central_chain_computationally_verified": True,
            "acceptance_blockers": acceptance_blockers,
        },
        "gate_assessment": gate_assessment,
        "event_design": {
            "area_operator_summary": area["summary"],
            "retained_event_count": input_manifest["event_count"],
            "retained_event_day_count": input_manifest["event_day_count"],
            "selection_exclusions": input_manifest["selection_exclusions"],
        },
        "central_source_mass_accounting": {
            "released_mass_kg_by_species": emissions_manifest[
                "mass_kg_by_species"
            ],
            "finite_window_fuel_balance": balance["totals"],
            "transport_scope": balance["transport_scope"],
        },
        "external_evaluations": {
            **evaluations,
            "aqs_pm25": {
                "artifact": _artifact(aqs_path),
                "assessment_role": aqs["assessment_role"],
                "acceptance_capable": aqs["acceptance_capable"],
                "passed": False,
                "not_evaluable": True,
                "pair_count": aqs["central_pairs"]["pair_count"],
                "rejection_counts": aqs["rejection_counts"],
            },
        },
        "sensitivities": {
            "artifact": _artifact(sensitivity_path),
            "emission_factor_bracket_ordered_for_every_species": sensitivities[
                "emission_factor_bracket_ordered_for_every_species"
            ],
            "comparisons": sensitivity_summary,
            "central_deposition_attribution": sensitivities[
                "central_deposition_attribution"
            ],
        },
        "software_verification": {
            "artifact": _artifact(software_verification_path),
            "results": software_verification,
        },
        "artifacts": {
            "assessment_builder": _artifact(
                repository_root
                / "scripts/build_smoke_validation_assessment_2026.py"
            ),
            "publication_methods": _artifact(
                repository_root / "docs/smoke-validation-methods-2026.md"
            ),
            "publication_results": _artifact(
                repository_root / "docs/smoke-validation-results-2026.md"
            ),
            "validation_log": _artifact(
                repository_root / "docs/smoke-validation-log.md"
            ),
            "protocol_chain": protocol_chain,
            "central_manifest": _artifact(manifest_path),
            "central_input_manifest": _artifact(input_manifest_path),
            "central_emissions_manifest": _artifact(emissions_manifest_path),
            "central_output_verification": _artifact(verifier_path),
            "cffeps_finite_window_balance": _artifact(balance_path),
            "mcd64a1_area_summary": _artifact(area_path),
            "gfas_source_bundle": _artifact(
                central / "evaluation/gfas/gfas-v1.4.2-source-days.grib"
            ),
            "gfas_pair_manifest": _artifact(
                central / "evaluation/gfas/pairs/manifest.json"
            ),
            "tropomi_pair_manifest": _artifact(
                central / "evaluation/tropomi/manifest.json"
            ),
            "airnow_pair_manifest": _artifact(
                central / "evaluation/airnow/manifest.json"
            ),
            "aqs_pair_manifest": _artifact(aqs_path),
        },
        "interpretation": {
            "permitted_claim": (
                "The frozen five-event CFFEPS--FLEXPART candidate completed "
                "and passed independent computational and mass-integrity "
                "checks; the reported diagnostic and provisional external "
                "comparisons and sensitivity results are reproducible."
            ),
            "prohibited_claims": [
                "scientific validation of the system for operational use",
                "population-wide performance across Canadian wildfire sizes",
                "unbiased source emissions relative to GFAS",
                "validated vertical injection or transported plume height",
                "validated surface PM2.5 prediction",
                "authorization to remove the simulation-write safety lock",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_root", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--generated-at",
        default=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args()
    report = build_assessment(
        experiment_root=args.experiment_root,
        repository_root=args.repository_root,
        generated_at=args.generated_at,
    )
    _atomic_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["decision"]["scientific_acceptance_status"],
                "acceptance_blocker_count": len(
                    report["decision"]["acceptance_blockers"]
                ),
                "output": args.output.resolve().as_posix(),
                "output_sha256": _sha256(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
