#!/usr/bin/env python3
"""Verify a completed frozen CFFEPS/FLEXPART candidate and its scientific files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import UTC
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
from weather_ingest.cffeps import read_emission_bundle, validate_emission_bundle


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_concentration(path: Path) -> dict[str, Any]:
    with netCDF4.Dataset(path) as dataset:
        dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
        if dimensions.get("time") != 24:
            raise ValueError(f"{path} does not contain 24 hourly fields")
        if dimensions.get("height") != 9:
            raise ValueError(f"{path} does not contain the frozen nine output heights")
        candidates = [name for name in dataset.variables if name.lower().endswith("_mr")]
        if candidates != ["spec001_mr"]:
            raise ValueError(f"{path} has an unexpected concentration variable set")
        values = np.ma.asarray(dataset.variables["spec001_mr"][:])
        values = values.compressed() if np.ma.isMaskedArray(values) else values.ravel()
        if values.size == 0 or not np.all(np.isfinite(values)) or np.any(values < 0):
            raise ValueError(f"{path} contains invalid concentrations")
        times = np.asarray(dataset.variables["time"][:], dtype=float)
        if not np.array_equal(times, np.arange(3600.0, 86401.0, 3600.0)):
            raise ValueError(f"{path} does not cover the frozen hourly interval")
        maximum = float(values.max())
        if maximum <= 0:
            raise ValueError(f"{path} contains no positive transported concentration")
        auxiliary_fields = {}
        for label, name in (
            ("wet_deposition", "WD_spec001"),
            ("dry_deposition", "DD_spec001"),
        ):
            if name not in dataset.variables:
                raise ValueError(f"{path} lacks {label}")
            deposition = np.ma.asarray(dataset.variables[name][:])
            deposition = (
                deposition.compressed()
                if np.ma.isMaskedArray(deposition)
                else deposition.ravel()
            )
            if (
                deposition.size == 0
                or not np.all(np.isfinite(deposition))
                or np.any(deposition < 0)
            ):
                raise ValueError(f"{path} contains invalid {label}")
            auxiliary_fields[label] = {
                "variable": name,
                "units": dataset.variables[name].units,
                "minimum": float(deposition.min()),
                "maximum": float(deposition.max()),
                "finite": True,
                "nonnegative": True,
            }
        return {
            "dimensions": dimensions,
            "concentration_variable": "spec001_mr",
            "concentration_units": dataset.variables["spec001_mr"].units,
            "minimum": float(values.min()),
            "maximum": maximum,
            "finite": True,
            "nonnegative": True,
            "auxiliary_fields": auxiliary_fields,
        }


def verify(candidate_directory: Path) -> dict[str, Any]:
    candidate_directory = candidate_directory.resolve()
    manifest_path = candidate_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("candidate manifest is not complete")

    emissions_path = candidate_directory / "input/emissions.nc"
    bundle_validation = validate_emission_bundle(emissions_path)
    rows = read_emission_bundle(emissions_path)
    expected_mass: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        day = row.source_time_start.astimezone(UTC).date().isoformat()
        expected_mass[(day, row.species)] += row.emitted_mass_kg

    member_reports: list[dict[str, Any]] = []
    seeds: set[int] = set()
    executable_hashes: set[str] = set()
    release_mass_by_species: dict[str, float] = defaultdict(float)
    particle_count = 0
    release_count = 0
    for day, day_manifest in sorted(manifest["transport_days"].items()):
        if day_manifest["source_day"] != day:
            raise ValueError("transport day key does not match its manifest")
        for species, result in sorted(day_manifest["results"].items()):
            if result["status"] != "complete" or result["exit_code"] != 0:
                raise ValueError(f"{day}/{species} did not complete")
            seed = int(result["random_seed"])
            if seed in seeds:
                raise ValueError("FLEXPART member random seed was reused")
            seeds.add(seed)
            executable_hashes.add(result["executable_sha256"])
            prepared = day_manifest["prepared_members"][species]
            release_summary = prepared["release_summary"]
            actual_mass = float(release_summary["mass_kg_by_species"][species])
            if not math.isclose(
                actual_mass,
                expected_mass[(day, species)],
                rel_tol=1e-10,
                abs_tol=1e-12,
            ):
                raise ValueError(f"{day}/{species} release mass does not match emissions")
            release_mass_by_species[species] += actual_mass
            particle_count += int(release_summary["particle_count"])
            release_count += int(release_summary["release_count"])

            run_directory = candidate_directory / "transport" / day / species.lower()
            run_log = run_directory / "run.log"
            if "CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!" not in (
                run_log.read_text(encoding="utf-8")
            ):
                raise ValueError(f"{day}/{species} lacks the FLEXPART completion marker")
            outputs = sorted((run_directory / "output").glob("grid_conc_*.nc"))
            if len(outputs) != 1 or result["output_count"] != 1:
                raise ValueError(f"{day}/{species} has an unexpected concentration file count")
            output = outputs[0]
            expected_hash = result["output_sha256"].get(output.name)
            if expected_hash is None or _sha256(output) != expected_hash:
                raise ValueError(f"{day}/{species} concentration checksum changed")
            member_reports.append(
                {
                    "source_day": day,
                    "species": species,
                    "random_seed": seed,
                    "release_mass_kg": actual_mass,
                    "particle_count": release_summary["particle_count"],
                    "release_count": release_summary["release_count"],
                    "wall_time_seconds": result["wall_time_seconds"],
                    "output_path": output.as_posix(),
                    "output_sha256": expected_hash,
                    "netcdf": _verify_concentration(output),
                }
            )

    if len(member_reports) != 24:
        raise ValueError(f"expected 24 transport members, found {len(member_reports)}")
    if len(executable_hashes) != 1:
        raise ValueError("multiple FLEXPART executables were used")
    return {
        "schema_version": 2,
        "candidate_version": manifest["candidate_version"],
        "status": "passed",
        "candidate_manifest": {
            "path": manifest_path.as_posix(),
            "sha256": _sha256(manifest_path),
        },
        "emissions": {
            "path": emissions_path.as_posix(),
            "sha256": _sha256(emissions_path),
            "bundle_validation": bundle_validation,
        },
        "member_count": len(member_reports),
        "unique_random_seed_count": len(seeds),
        "flexpart_executable_sha256": next(iter(executable_hashes)),
        "particle_count": particle_count,
        "release_count": release_count,
        "release_mass_kg_by_species": dict(sorted(release_mass_by_species.items())),
        "checks": {
            "all_members_completed": True,
            "all_completion_markers_present": True,
            "release_mass_matches_emission_bundle": True,
            "all_concentration_hashes_match": True,
            "all_concentrations_finite_nonnegative_and_nonzero": True,
            "all_deposition_fields_finite_and_nonnegative": True,
            "all_members_have_24_hourly_fields": True,
            "all_member_seeds_unique": True,
        },
        "members": member_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.candidate_directory)
    except Exception as exc:
        report = {
            "schema_version": 2,
            "candidate_directory": args.candidate_directory.resolve().as_posix(),
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _atomic_json(args.output, report)
        print(
            json.dumps(
                {
                    "status": "failed",
                    "output": args.output.resolve().as_posix(),
                    "output_sha256": _sha256(args.output),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    _atomic_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "member_count": report["member_count"],
                "particle_count": report["particle_count"],
                "release_count": report["release_count"],
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
