#!/usr/bin/env python3
"""Verify complete outputs, mass bounds, and thread pairs for the W5 matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset
from pyproj import Geod
from weather_ingest.flexpart_releases import parse_release_mass

SUCCESS_TEXT = "CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!"
PARTICLE_LINE = re.compile(
    r"Time:\s+(?P<time>\d+) seconds\. Total spawned:\s+(?P<spawned>\d+) "
    r"alive:\s+(?P<alive>\d+) terminated:\s+(?P<terminated>\d+)"
)


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


def dimension_sizes(dataset: Dataset) -> dict[str, int]:
    return {name: len(value) for name, value in dataset.dimensions.items()}


def scientific_variable(name: str) -> bool:
    return (
        name.startswith("DD_spec")
        or name.startswith("WD_spec")
        or (name.startswith("spec") and name.endswith(("_mr", "_pptv")))
    )


def scan_netcdf(path: Path) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    nonfinite_count = 0
    negative_science_count = 0
    with Dataset(path) as dataset:
        for name, variable in dataset.variables.items():
            if variable.dtype.kind not in {"i", "u", "f"}:
                continue
            values = variable[:]
            mask = np.ma.getmaskarray(values)
            array = np.asarray(values.filled(np.nan) if np.ma.isMaskedArray(values) else values)
            numeric = array.astype(np.float64, copy=False)
            invalid = (~mask) & ~np.isfinite(numeric)
            invalid_count = int(np.count_nonzero(invalid))
            negative_count = (
                int(np.count_nonzero((~mask) & (numeric < 0)))
                if scientific_variable(name)
                else 0
            )
            nonfinite_count += invalid_count
            negative_science_count += negative_count
            variables[name] = {
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "masked_count": int(np.count_nonzero(mask)),
                "nonfinite_count": invalid_count,
                "negative_science_count": negative_count,
            }
        return {
            "path": str(path),
            "sha256": sha256(path),
            "dimensions": dimension_sizes(dataset),
            "variables": variables,
            "nonfinite_count": nonfinite_count,
            "negative_science_count": negative_science_count,
        }


def coordinate_edges(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float64)
    if len(values) < 2:
        raise ValueError("at least two coordinates are required")
    edges = np.empty(len(values) + 1)
    edges[1:-1] = (values[:-1] + values[1:]) / 2
    edges[0] = values[0] - (values[1] - values[0]) / 2
    edges[-1] = values[-1] + (values[-1] - values[-2]) / 2
    return edges


def grid_cell_areas(longitudes: np.ndarray, latitudes: np.ndarray) -> np.ndarray:
    lon_edges = coordinate_edges(longitudes)
    lat_edges = coordinate_edges(latitudes)
    geod = Geod(ellps="WGS84")
    result = np.empty((len(latitudes), len(longitudes)), dtype=np.float64)
    for row in range(len(latitudes)):
        for column in range(len(longitudes)):
            area, _perimeter = geod.polygon_area_perimeter(
                [
                    lon_edges[column],
                    lon_edges[column + 1],
                    lon_edges[column + 1],
                    lon_edges[column],
                ],
                [
                    lat_edges[row],
                    lat_edges[row],
                    lat_edges[row + 1],
                    lat_edges[row + 1],
                ],
            )
            result[row, column] = abs(area)
    return result


def deposition_mass(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    with Dataset(path) as dataset:
        areas = grid_cell_areas(
            np.asarray(dataset.variables["longitude"][:]),
            np.asarray(dataset.variables["latitude"][:]),
        )
        for name, variable in dataset.variables.items():
            if not (name.startswith("DD_spec") or name.startswith("WD_spec")):
                continue
            if str(getattr(variable, "units", "")) != "1e-12 kg m-2":
                raise ValueError(f"unexpected deposition units for {name}")
            values = np.asarray(variable[:], dtype=np.float64)
            dimensions = list(variable.dimensions)
            time_axis = dimensions.index("time")
            final = np.take(values, -1, axis=time_axis)
            while final.ndim > 2:
                final = final.sum(axis=0)
            result[name] = float(np.sum(final * areas) * 1.0e-12)
    return result


def array_pair(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    left64 = np.asarray(left, dtype=np.float64).ravel()
    right64 = np.asarray(right, dtype=np.float64).ravel()
    denominator = float(np.sum(np.abs(right64)))
    normalized_l1 = (
        float(np.sum(np.abs(left64 - right64)) / denominator)
        if denominator > 0
        else (0.0 if np.array_equal(left64, right64) else math.inf)
    )
    active = (left64 != 0) | (right64 != 0)
    if np.count_nonzero(active) >= 2:
        correlation = float(np.corrcoef(left64[active], right64[active])[0, 1])
    else:
        correlation = 1.0 if np.array_equal(left64, right64) else math.nan
    return {
        "normalized_l1": normalized_l1,
        "active_union_pearson_r": correlation,
    }


def compare_thread_pair(one: Path, eight: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    with Dataset(one) as left, Dataset(eight) as right:
        if dimension_sizes(left) != dimension_sizes(right):
            raise ValueError("thread-pair dimensions differ")
        for name in sorted(set(left.variables) & set(right.variables)):
            if not scientific_variable(name):
                continue
            report[name] = array_pair(left.variables[name][:], right.variables[name][:])
    concentration = next(
        value for name, value in report.items() if name.startswith("spec") and name.endswith("_mr")
    )
    return {
        "variables": report,
        "pilot_informed_concentration_diagnostic": {
            "acceptance_role": "advisory_not_preregistered",
            "normalized_l1_maximum": 0.02,
            "active_union_pearson_r_minimum": 0.999,
            "within_proposed_bound": (
                concentration["normalized_l1"] <= 0.02
                and concentration["active_union_pearson_r"] >= 0.999
            ),
            "reason": (
                "W5 states that this pilot-informed proposal requires reviewer "
                "input before it can become a field-equivalence acceptance gate."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--source-verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    run_manifest = json.loads(arguments.run_manifest.read_text(encoding="utf-8"))
    source_verification = json.loads(
        arguments.source_verification.read_text(encoding="utf-8")
    )
    expected = {
        (item["source_day"], str(item["species"]).lower()): item
        for item in source_verification["members"]
    }
    source_attempt = Path(run_manifest["source_attempt"])
    records = run_manifest["records"]
    if len(records) != 48:
        raise ValueError(f"W5 matrix has {len(records)} attempts, expected 48")

    attempts: list[dict[str, Any]] = []
    pair_paths: dict[tuple[str, str], dict[int, Path]] = defaultdict(dict)
    hard_failures: list[str] = []
    for record in records:
        key = record["day"], record["species"]
        expectation = expected[key]
        attempt = Path(record["attempt"])
        manifest_path = attempt / "attempt-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_directory = attempt / "output"
        source_output = source_attempt / "transport" / key[0] / key[1] / "output"
        output_names = sorted(
            path.name for path in output_directory.iterdir() if path.is_file()
        )
        source_names = sorted(path.name for path in source_output.iterdir() if path.is_file())
        grid_path = next(output_directory.glob("grid_conc_*.nc"))
        source_grid = next(source_output.glob("grid_conc_*.nc"))
        scans = [
            scan_netcdf(path)
            for path in sorted(output_directory.glob("*.nc"))
        ]
        log = (attempt / "run.log").read_text(encoding="utf-8")
        particle_lines = [match.groupdict() for match in PARTICLE_LINE.finditer(log)]
        final_particles = particle_lines[-1] if particle_lines else None
        masses, particles = parse_release_mass(attempt / "options/RELEASES", 1)
        release_mass = sum(item[0] for item in masses)
        deposition = deposition_mass(grid_path)
        deposited_mass = sum(deposition.values())
        with Dataset(grid_path) as candidate, Dataset(source_grid) as source_dataset:
            structure_exact = (
                dimension_sizes(candidate) == dimension_sizes(source_dataset)
                and {
                    name: (variable.dimensions, variable.shape)
                    for name, variable in candidate.variables.items()
                }
                == {
                    name: (variable.dimensions, variable.shape)
                    for name, variable in source_dataset.variables.items()
                }
            )
        checks = {
            "attempt_completed": (
                manifest.get("error") is None
                and manifest.get("result", {}).get("status") == "complete"
            ),
            "seed_exact": manifest.get("random_seed") == expectation["random_seed"],
            "success_banner_present": SUCCESS_TEXT in log,
            "particle_accounting_closed": (
                final_particles is not None
                and int(final_particles["spawned"])
                == int(final_particles["alive"]) + int(final_particles["terminated"])
            ),
            "output_inventory_exact": output_names == source_names,
            "netcdf_structure_exact": structure_exact,
            "all_netcdf_numeric_values_finite": all(
                scan["nonfinite_count"] == 0 for scan in scans
            ),
            "all_science_fields_nonnegative": all(
                scan["negative_science_count"] == 0 for scan in scans
            ),
            "release_mass_exact": math.isclose(
                release_mass,
                float(expectation["release_mass_kg"]),
                rel_tol=0,
                abs_tol=1.0e-6,
            ),
            "particle_count_exact": particles == int(expectation["particle_count"]),
            "deposition_not_greater_than_release": (
                deposited_mass <= release_mass * (1 + 1.0e-6)
            ),
        }
        if not all(checks.values()):
            hard_failures.append(
                f"{key[0]}/{key[1]}/threads-{record['threads']}: "
                + ",".join(name for name, passed in checks.items() if not passed)
            )
        attempts.append(
            {
                **record,
                "attempt_manifest_sha256": sha256(manifest_path),
                "release_mass_kg": release_mass,
                "release_particle_count": particles,
                "deposition_mass_kg": deposition,
                "total_deposition_mass_kg": deposited_mass,
                "netcdf_scans": scans,
                "final_particle_accounting": final_particles,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
        pair_paths[key][int(record["threads"])] = grid_path

    pairs = []
    advisory_exceedances = []
    for key in sorted(pair_paths):
        if set(pair_paths[key]) != {1, 8}:
            hard_failures.append(f"{key[0]}/{key[1]} lacks a 1/8 thread pair")
            continue
        comparison = compare_thread_pair(pair_paths[key][1], pair_paths[key][8])
        diagnostic = comparison["pilot_informed_concentration_diagnostic"]
        if not diagnostic["within_proposed_bound"]:
            advisory_exceedances.append(
                f"{key[0]}/{key[1]} exceeds the proposed concentration bound"
            )
        pairs.append(
            {
                "day": key[0],
                "species": key[1],
                **comparison,
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "w5-complete-output-member-matrix-verification",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run_manifest": {
            "path": str(arguments.run_manifest),
            "sha256": sha256(arguments.run_manifest),
        },
        "source_verification": {
            "path": str(arguments.source_verification),
            "sha256": sha256(arguments.source_verification),
        },
        "attempt_count": len(attempts),
        "passed_attempt_count": sum(item["passed"] for item in attempts),
        "thread_pair_count": len(pairs),
        "hard_failure_count": len(hard_failures),
        "hard_failures": hard_failures,
        "advisory_exceedance_count": len(advisory_exceedances),
        "advisory_exceedances": advisory_exceedances,
        "passed_hard_requirements": not hard_failures,
        "passed": not hard_failures,
        "attempts": attempts,
        "thread_pairs": pairs,
    }
    atomic_json(arguments.output, payload)
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "sha256": sha256(arguments.output),
                "attempt_count": len(attempts),
                "passed_attempt_count": payload["passed_attempt_count"],
                "thread_pair_count": len(pairs),
                "hard_failures": hard_failures,
                "advisory_exceedances": advisory_exceedances,
                "passed": payload["passed"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
