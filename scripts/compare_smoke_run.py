#!/usr/bin/env python3
"""Compare archived smoke-run scientific NetCDF outputs and provenance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import netCDF4
import numpy as np


def load(root: Path, run_id: UUID) -> tuple[Path, dict[str, object]]:
    run_dir = root / "derived/smoke/runs" / str(run_id)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No archived manifest for run {run_id}")
    return run_dir, json.loads(manifest_path.read_text(encoding="utf-8"))


def _stochastic_field(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(("spec", "dd_", "wd_"))


def compare_netcdf(
    left: Path,
    right: Path,
    rtol: float,
    atol: float,
    aggregate_rtol: float,
) -> str:
    exact = True
    pointwise_tolerant = True
    with netCDF4.Dataset(left) as left_ds, netCDF4.Dataset(right) as right_ds:
        if {name: len(dim) for name, dim in left_ds.dimensions.items()} != {
            name: len(dim) for name, dim in right_ds.dimensions.items()
        }:
            return "CHANGED"
        if set(left_ds.variables) != set(right_ds.variables):
            return "CHANGED"
        for name in left_ds.variables:
            left_value = np.ma.asarray(left_ds.variables[name][:])
            right_value = np.ma.asarray(right_ds.variables[name][:])
            if not np.array_equal(np.ma.getmaskarray(left_value), np.ma.getmaskarray(right_value)):
                return "CHANGED"
            left_data = left_value.compressed()
            right_data = right_value.compressed()
            if left_data.dtype.kind in "fci":
                if not np.all(np.isfinite(left_data)) or not np.all(np.isfinite(right_data)):
                    return "CHANGED"
                arrays_exact = np.array_equal(left_data, right_data)
                arrays_close = np.allclose(left_data, right_data, rtol=rtol, atol=atol)
                exact = exact and arrays_exact
                pointwise_tolerant = pointwise_tolerant and arrays_close
                if not arrays_close:
                    if not _stochastic_field(name):
                        return "CHANGED"
                    if np.min(left_data) < -atol or np.min(right_data) < -atol:
                        return "CHANGED"
                    left_total = float(np.sum(left_data, dtype=np.float64))
                    right_total = float(np.sum(right_data, dtype=np.float64))
                    denominator = max(abs(left_total), abs(right_total), atol)
                    if abs(left_total - right_total) / denominator > aggregate_rtol:
                        return "CHANGED"
            elif not np.array_equal(left_data, right_data):
                return "CHANGED"
    if exact:
        return "EXACT"
    return "TOLERANT" if pointwise_tolerant else "INVARIANT"


def member_netcdf(run_dir: Path, species: str) -> Path:
    matches = list((run_dir / "transport" / species.lower() / "output").glob("grid_conc_*.nc"))
    if len(matches) != 1:
        raise ValueError(f"Expected one {species} NetCDF output")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=UUID)
    parser.add_argument("reference_run_id", type=UUID)
    parser.add_argument("--rtol", type=float, default=1e-6)
    parser.add_argument("--atol", type=float, default=1e-12)
    parser.add_argument(
        "--aggregate-rtol",
        type=float,
        default=0.1,
        help="maximum relative total difference for nonnegative stochastic fields",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data")),
    )
    args = parser.parse_args()
    root = args.data_root.resolve()
    candidate_dir, candidate = load(root, args.run_id)
    reference_dir, reference = load(root, args.reference_run_id)
    species = sorted(set(candidate["member_manifests"]) | set(reference["member_manifests"]))
    results = {
        item: compare_netcdf(
            member_netcdf(candidate_dir, item),
            member_netcdf(reference_dir, item),
            args.rtol,
            args.atol,
            args.aggregate_rtol,
        )
        if item in candidate["member_manifests"] and item in reference["member_manifests"]
        else "CHANGED"
        for item in species
    }
    provenance = {
        field: candidate[field] == reference[field]
        for field in (
            "scenario_config_sha256",
            "gfs_manifest_sha256",
            "event_snapshot_sha256",
            "cffeps_executable_sha256",
            "flexpart_executable_sha256",
        )
    }
    report = {
        "candidate_run_id": str(args.run_id),
        "reference_run_id": str(args.reference_run_id),
        "scientific_outputs": results,
        "provenance_equal": provenance,
        "mass_kg_by_species": {
            "candidate": candidate["mass_kg_by_species"],
            "reference": reference["mass_kg_by_species"],
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if "CHANGED" in results.values() else 0


if __name__ == "__main__":
    raise SystemExit(main())
