#!/usr/bin/env python3
"""Freeze the technical W5 production-correction evidence package."""

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


def artifact(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--investigation-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.investigation_root.resolve()
    production = root / "production-fix-2026-07-26"
    full_matrix = production / "full-member-matrix"

    suite = Path(
        "flexpart/tests/regression_suite/candidates/"
        "w5-zero-skew-production-20260726/suite_manifest.json"
    )
    comparison = Path(
        "flexpart/tests/regression_suite/candidates/"
        "w5-zero-skew-production-20260726-comparison.json"
    )
    invariants = Path(
        "flexpart/tests/regression_suite/candidates/"
        "w5-zero-skew-production-20260726-invariants.json"
    )
    suite_payload = json.loads(suite.read_text(encoding="utf-8"))
    matrix_verification = full_matrix / "complete-output-verification.json"
    verification_payload = json.loads(matrix_verification.read_text(encoding="utf-8"))
    if not suite_payload.get("passed"):
        raise ValueError("22-case compact FLEXPART suite did not pass")
    if not verification_payload.get("passed_hard_requirements"):
        raise ValueError("full W5 member matrix did not pass its hard requirements")

    payload = {
        "schema_version": 1,
        "artifact_type": "flexpart-w5-technical-completion-manifest",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "program_id": "cffeps-flexpart-acceptance-program-v1",
        "workstream": "W5",
        "status": "technical_complete_awaiting_independent_review",
        "scientific_acceptance_claimed": False,
        "production_writes_enabled": False,
        "correction": {
            "location": "reinit_particle in cbl_mod.f90",
            "root_cause": (
                "At exact zero skew, the recovery distribution evaluated 0/0; "
                "reinitialization returned NaN and a later zero wet-deposition "
                "increment multiplied by NaN grid weights."
            ),
            "change": (
                "Use the existing signed cube-root helper and the symmetric "
                "zero-skew limit r=0, sqrt(r)=0."
            ),
            "final_array_sanitization": False,
            "source": artifact(Path("flexpart/src/cbl_mod.f90")),
            "meter_executable": artifact(Path("flexpart/src/FLEXPART")),
            "eta_executable": artifact(Path("flexpart/src/FLEXPART_ETA")),
            "pre_fix_meter_executable": artifact(
                production / "pre-fix-executables/FLEXPART"
            ),
            "pre_fix_eta_executable": artifact(
                production / "pre-fix-executables/FLEXPART_ETA"
            ),
        },
        "focused_regression": {
            "status": "passes_corrected_source_and_fails_preserved_pre_fix_source",
            "runner": artifact(Path("flexpart/tests/cbl_zero_skew/run_test.sh")),
            "program": artifact(
                Path("flexpart/tests/cbl_zero_skew/test_cbl_zero_skew.f90")
            ),
        },
        "compact_flexpart_regression": {
            "passed_cases": suite_payload["case_count"],
            "failed_cases": suite_payload["failed_count"],
            "suite_manifest": artifact(suite),
            "comparison": artifact(comparison),
            "invariant_verification": artifact(invariants),
        },
        "full_member_matrix": {
            "attempt_count": verification_payload["attempt_count"],
            "passed_attempt_count": verification_payload["passed_attempt_count"],
            "thread_pair_count": verification_payload["thread_pair_count"],
            "hard_failure_count": verification_payload["hard_failure_count"],
            "advisory_exceedance_count": verification_payload[
                "advisory_exceedance_count"
            ],
            "run_manifest": artifact(full_matrix / "member-matrix-run-manifest.json"),
            "complete_output_verification": artifact(matrix_verification),
            "failing_member_1_2_4_8_matrix": artifact(
                production / "post-fix-thread-matrix.json"
            ),
            "hard_checks": [
                "all numeric NetCDF fields finite",
                "all concentration/deposition fields non-negative",
                "no masked values in valid output",
                "output inventory and NetCDF structure exact",
                "release mass and particle count exact",
                "successful model termination and closed particle accounting",
                "cumulative deposition mass not greater than release mass",
            ],
            "thread_equivalence_diagnostic": (
                "The proposed 2% normalized-L1 and R>=0.999 concentration "
                "bound remains advisory pending independent reviewer freeze."
            ),
        },
        "other_regression_results": {
            "cffeps_golden_cases_passed": 10,
            "fbp_sensitivity_cases_passed": 6,
            "python_tests_passed": 223,
            "python_tests_skipped": 19,
            "python_skip_reason": (
                "PostgreSQL integration tests require WEATHER_TEST_DATABASE_URL"
            ),
        },
        "remaining_governance": [
            "independent numerical code review",
            "independent emissions-science review that the correction is not output sanitization",
            "reviewer decision on whether to adopt a thread-equivalence engineering bound",
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
