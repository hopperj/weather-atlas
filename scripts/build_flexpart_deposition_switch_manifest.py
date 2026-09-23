#!/usr/bin/env python3
"""Freeze technical evidence for W6 wet/dry switches with settling retained."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _science_field_integrity(suite_root: Path, suite: dict[str, Any]) -> dict[str, Any]:
    nonfinite = 0
    negative_concentration_or_deposition = 0
    numeric_field_count = 0
    for record in suite["cases"].values():
        manifest = json.loads((suite_root / record["manifest"]).read_text())
        for output in manifest["outputs"].values():
            netcdf = output.get("netcdf")
            if not netcdf:
                continue
            for name, variable in netcdf["variables"].items():
                numeric_field_count += "finite_count" in variable
                nonfinite += int(variable.get("nan_count", 0))
                nonfinite += int(variable.get("positive_inf_count", 0))
                nonfinite += int(variable.get("negative_inf_count", 0))
                if (
                    name.startswith(("spec", "WD_", "DD_"))
                    and variable.get("finite_count", 0)
                    and float(variable["min"]) < 0
                ):
                    negative_concentration_or_deposition += 1
    return {
        "numeric_field_count": numeric_field_count,
        "nonfinite_value_count": nonfinite,
        "negative_concentration_or_deposition_field_count": (
            negative_concentration_or_deposition
        ),
        "passed": nonfinite == 0 and negative_concentration_or_deposition == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w5-manifest", type=Path, required=True)
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--invariants", type=Path, required=True)
    parser.add_argument("--matrix-manifest", type=Path, required=True)
    parser.add_argument("--event-area-report", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    suite_path = arguments.suite_root / "suite_manifest.json"
    suite = json.loads(suite_path.read_text())
    comparison = json.loads(arguments.comparison.read_text())
    invariants = json.loads(arguments.invariants.read_text())
    matrix = json.loads(arguments.matrix_manifest.read_text())
    if not suite.get("passed") or suite.get("case_count") != 22:
        raise ValueError("deposition-switch regression suite did not pass all 22 cases")
    if matrix.get("status") != "frozen":
        raise ValueError("W6 sensitivity matrix is not frozen")

    unchanged_deposition_cases = {}
    for case in ("07_aerosol_deposition_settling", "08_gas_wet_dry_deposition"):
        record = comparison["cases"][case]
        command_only = record["notes"] == ["COMMAND.namelist: binary SHA-256 differs"]
        unchanged_deposition_cases[case] = {
            "command_schema_only_difference": command_only,
            "all_scientific_outputs_exact": command_only,
        }
    required_invariant_cases = (
        "07_aerosol_deposition_settling",
        "08_gas_wet_dry_deposition",
        "22_parallel_stress",
    )
    required_invariants_passed = all(
        invariants["cases"][case]["valid"] for case in required_invariant_cases
    )
    restart = invariants["cases"]["19_restart_read"]
    restart_exception_bounded = (
        restart["notes"] == ["input inventory or content differs"]
        and restart["output_inventory_exact"]
        and restart["totals_exact"]
        and restart["candidate_nonfinite_count"] <= restart["baseline_nonfinite_count"]
    )
    integrity = _science_field_integrity(arguments.suite_root, suite)
    technical_passed = (
        all(item["all_scientific_outputs_exact"] for item in unchanged_deposition_cases.values())
        and required_invariants_passed
        and restart_exception_bounded
        and integrity["passed"]
    )
    if not technical_passed:
        raise ValueError("deposition-switch extension failed its technical evidence rules")

    payload = {
        "schema_version": 1,
        "artifact_type": "flexpart-deposition-switch-technical-evidence",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "technical_complete_awaiting_independent_review",
        "scientific_acceptance_claimed": False,
        "production_writes_enabled": False,
        "purpose": (
            "Allow wet and dry deposition sensitivity switches while retaining "
            "the species density/diameter state used by gravitational settling."
        ),
        "implementation": {
            "mechanism": (
                "Species physics are initialized first; COMMAND masks wet/dry "
                "deposition arrays afterward and never changes settling state. "
                "Deposition kernels use FLOOR at lower grid boundaries so "
                "outside-domain particles cannot create negative weights."
            ),
            "settling_fixed_true": True,
            "sources": [
                _artifact(path)
                for path in (
                    Path("flexpart/src/com_mod.f90"),
                    Path("flexpart/src/readoptions_mod.f90"),
                    Path("flexpart/src/drydepo_mod.f90"),
                    Path("flexpart/src/wetdepo_mod.f90"),
                    Path("python/weather_ingest/flexpart_config.py"),
                    Path("python/weather_ingest/flexpart_runner.py"),
                    Path("python/weather_ingest/smoke_validation_candidate.py"),
                )
            ],
            "executable": _artifact(arguments.executable),
        },
        "regression": {
            "suite": _artifact(suite_path),
            "comparison": _artifact(arguments.comparison),
            "invariants": _artifact(arguments.invariants),
            "case_count": suite["case_count"],
            "failed_case_count": suite["failed_count"],
            "unchanged_default_deposition_cases": unchanged_deposition_cases,
            "required_invariant_cases": list(required_invariant_cases),
            "required_invariants_passed": required_invariants_passed,
            "restart_exception": {
                "bounded": restart_exception_bounded,
                "reason": (
                    "The restart source now contains the two new default-true "
                    "COMMAND namelist fields; output inventory and totals arrays "
                    "remain exact."
                ),
            },
            "whole_suite_science_field_integrity": integrity,
        },
        "w6": {
            "matrix": _artifact(arguments.matrix_manifest),
            "event_area_report": _artifact(arguments.event_area_report),
            "matrix_member_count": matrix["member_count"],
            "deposition_reference": "central wet+dry member",
            "deposition_sensitivities": ["no-wet", "no-dry", "none"],
        },
        "prior_w5_evidence": _artifact(arguments.w5_manifest),
        "remaining_governance": [
            "independent numerical review of the post-species masking location",
            "independent emissions-science review of retaining settling",
            "complete W6 candidate execution after Phase 0 authorization",
        ],
    }
    _write(arguments.output, payload)
    print(
        json.dumps(
            {
                "output": arguments.output.resolve().as_posix(),
                "sha256": _sha256(arguments.output),
                "status": payload["status"],
                "regression_cases_passed": suite["case_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
