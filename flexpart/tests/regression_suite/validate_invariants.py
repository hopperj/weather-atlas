#!/usr/bin/env python3
"""Validate run-wide invariants that stochastic spatial fields cannot compare bitwise."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_case(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / "cases" / name / "manifest.json").read_text())


def scientific_hash(entry: dict[str, Any]) -> str | None:
    netcdf = entry.get("netcdf")
    return netcdf.get("scientific_sha256") if netcdf else None


def nonfinite_count(outputs: dict[str, Any]) -> int:
    total = 0
    for entry in outputs.values():
        netcdf = entry.get("netcdf")
        if not netcdf:
            continue
        for variable in netcdf["variables"].values():
            total += int(variable.get("nan_count", 0))
            total += int(variable.get("positive_inf_count", 0))
            total += int(variable.get("negative_inf_count", 0))
    return total


def stable_input_hashes(inputs: dict[str, Any]) -> dict[str, str]:
    """Exclude copied restart NetCDF containers with volatile history metadata."""
    return {
        key: value["sha256"]
        for key, value in inputs.items()
        if not (key.startswith("restart_source/") and key.endswith(".nc"))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    candidate = args.candidate.resolve()
    left_suite = json.loads((baseline / "suite_manifest.json").read_text())
    right_suite = json.loads((candidate / "suite_manifest.json").read_text())
    names = sorted(set(left_suite["cases"]) | set(right_suite["cases"]))

    cases: dict[str, Any] = {}
    valid = True
    for name in names:
        notes: list[str] = []
        if name not in left_suite["cases"] or name not in right_suite["cases"]:
            notes.append("case missing")
            cases[name] = {"valid": False, "notes": notes}
            valid = False
            continue
        left = load_case(baseline, name)
        right = load_case(candidate, name)
        if not right["passed"]:
            notes.append("candidate execution failed")

        left_inputs = stable_input_hashes(left["inputs"])
        right_inputs = stable_input_hashes(right["inputs"])
        if left_inputs != right_inputs:
            notes.append("input inventory or content differs")
        if set(left["outputs"]) != set(right["outputs"]):
            notes.append("output inventory differs")

        left_totals = left["outputs"].get("totals.nc")
        right_totals = right["outputs"].get("totals.nc")
        totals_exact = bool(
            left_totals
            and right_totals
            and scientific_hash(left_totals) == scientific_hash(right_totals)
        )
        if not totals_exact:
            notes.append("totals.nc scientific arrays differ")

        left_nonfinite = nonfinite_count(left["outputs"])
        right_nonfinite = nonfinite_count(right["outputs"])
        if right_nonfinite > left_nonfinite:
            notes.append(
                f"new non-finite values: baseline={left_nonfinite}, "
                f"candidate={right_nonfinite}"
            )

        case_valid = not notes
        valid &= case_valid
        cases[name] = {
            "valid": case_valid,
            "inputs_exact": left_inputs == right_inputs,
            "output_inventory_exact": set(left["outputs"]) == set(right["outputs"]),
            "totals_exact": totals_exact,
            "baseline_nonfinite_count": left_nonfinite,
            "candidate_nonfinite_count": right_nonfinite,
            "notes": notes,
        }
        print(f"[{'PASS' if case_valid else 'FAIL'}] {name}")
        for note in notes:
            print(f"  {note}")

    result = {
        "baseline": str(baseline),
        "candidate": str(candidate),
        "valid": valid,
        "case_count": len(cases),
        "valid_case_count": sum(item["valid"] for item in cases.values()),
        "cases": cases,
    }
    output = args.output.resolve() if args.output else candidate / "invariants.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Invariant report written to {output}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
