#!/usr/bin/env python3
"""Compare two FLEXPART regression-suite artifact roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


def compare_netcdf(
    baseline: Path, candidate: Path, rtol: float, atol: float
) -> tuple[bool, bool, list[str]]:
    exact = True
    tolerant = True
    notes: list[str] = []
    with Dataset(baseline) as left, Dataset(candidate) as right:
        left_names = set(left.variables)
        right_names = set(right.variables)
        if left_names != right_names:
            missing = sorted(left_names - right_names)
            extra = sorted(right_names - left_names)
            notes.append(f"variables differ: missing={missing}, extra={extra}")
            return False, False, notes
        for name in sorted(left_names):
            lvar = left.variables[name]
            rvar = right.variables[name]
            if lvar.dimensions != rvar.dimensions or lvar.shape != rvar.shape:
                notes.append(
                    f"{name}: structure differs "
                    f"{lvar.dimensions}{lvar.shape} != {rvar.dimensions}{rvar.shape}"
                )
                exact = tolerant = False
                continue
            lval = lvar[:]
            rval = rvar[:]
            lmask = np.ma.getmaskarray(lval)
            rmask = np.ma.getmaskarray(rval)
            if not np.array_equal(lmask, rmask):
                notes.append(f"{name}: missing-value mask differs")
                exact = tolerant = False
                continue
            la = np.asarray(lval.filled(0) if np.ma.isMaskedArray(lval) else lval)
            ra = np.asarray(rval.filled(0) if np.ma.isMaskedArray(rval) else rval)
            numeric = np.issubdtype(la.dtype, np.number)
            values_equal = (
                np.array_equal(la, ra, equal_nan=True)
                if numeric
                else np.array_equal(la, ra)
            )
            if values_equal:
                continue
            exact = False
            if numeric:
                close = np.allclose(la, ra, rtol=rtol, atol=atol, equal_nan=True)
                if not close:
                    tolerant = False
                finite = np.isfinite(la) & np.isfinite(ra)
                max_abs = (
                    float(np.max(np.abs(la[finite] - ra[finite])))
                    if np.any(finite) else float("nan")
                )
                denom = np.maximum(np.abs(la[finite]), atol)
                max_rel = (
                    float(np.max(np.abs(la[finite] - ra[finite]) / denom))
                    if np.any(finite) else float("nan")
                )
                notes.append(
                    f"{name}: numeric difference, allclose={close}, "
                    f"max_abs={max_abs:.9g}, max_rel={max_rel:.9g}"
                )
            else:
                tolerant = False
                notes.append(f"{name}: non-numeric values differ")
    return exact, tolerant, notes


def load_manifest(root: Path, case: str) -> dict[str, Any]:
    return json.loads((root / "cases" / case / "manifest.json").read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--rtol", type=float, default=1.0e-6)
    parser.add_argument("--atol", type=float, default=1.0e-12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    candidate = args.candidate.resolve()
    left_suite = json.loads((baseline / "suite_manifest.json").read_text())
    right_suite = json.loads((candidate / "suite_manifest.json").read_text())
    cases = sorted(set(left_suite["cases"]) | set(right_suite["cases"]))

    all_exact = True
    all_tolerant = True
    report: dict[str, Any] = {}
    for case in cases:
        if case not in left_suite["cases"] or case not in right_suite["cases"]:
            report[case] = {"exact": False, "tolerant": False, "notes": ["case missing"]}
            all_exact = all_tolerant = False
            continue
        left = load_manifest(baseline, case)
        right = load_manifest(candidate, case)
        names = sorted(set(left["outputs"]) | set(right["outputs"]))
        case_exact = True
        case_tolerant = True
        notes: list[str] = []
        for name in names:
            if name not in left["outputs"] or name not in right["outputs"]:
                notes.append(f"{name}: output missing")
                case_exact = case_tolerant = False
                continue
            left_path = baseline / "cases" / case / "outputs" / name
            right_path = candidate / "cases" / case / "outputs" / name
            if name.endswith(".nc"):
                exact, tolerant, variable_notes = compare_netcdf(
                    left_path, right_path, args.rtol, args.atol
                )
                case_exact &= exact
                case_tolerant &= tolerant
                notes.extend(f"{name}: {note}" for note in variable_notes)
            else:
                same = left["outputs"][name]["sha256"] == right["outputs"][name]["sha256"]
                case_exact &= same
                case_tolerant &= same
                if not same:
                    notes.append(f"{name}: binary SHA-256 differs")
        report[case] = {
            "exact": case_exact,
            "tolerant": case_tolerant,
            "notes": notes,
        }
        all_exact &= case_exact
        all_tolerant &= case_tolerant
        print(
            f"[{'EXACT' if case_exact else 'TOLERANT' if case_tolerant else 'CHANGED'}] "
            f"{case}"
        )
        for note in notes:
            print(f"  {note}")

    result = {
        "baseline": str(baseline),
        "candidate": str(candidate),
        "rtol": args.rtol,
        "atol": args.atol,
        "all_exact": all_exact,
        "all_tolerant": all_tolerant,
        "cases": report,
        "exact_case_count": sum(item["exact"] for item in report.values()),
        "tolerant_case_count": sum(item["tolerant"] for item in report.values()),
        "changed_case_count": sum(not item["tolerant"] for item in report.values()),
    }
    output = (
        args.output.resolve()
        if args.output
        else candidate / "comparison.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Comparison written to {output}")
    return 0 if all_tolerant else 1


if __name__ == "__main__":
    raise SystemExit(main())
