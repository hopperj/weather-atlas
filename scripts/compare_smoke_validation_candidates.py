#!/usr/bin/env python3
"""Compare frozen smoke sensitivity fields and integrate central deposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
from pyproj import Geod

FIELDS = {
    "concentration": "spec001_mr",
    "wet_deposition": "WD_spec001",
    "dry_deposition": "DD_spec001",
}


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


def _output(candidate: Path, day: str, species: str) -> Path:
    matches = sorted(
        (candidate / "transport" / day / species.lower() / "output").glob(
            "grid_conc_*.nc"
        )
    )
    if len(matches) != 1:
        raise ValueError(f"expected one output for {candidate}/{day}/{species}")
    return matches[0]


def _array(variable: Any) -> np.ndarray:
    return np.asarray(np.ma.filled(variable[:], np.nan), dtype=np.float64)


class FieldAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.central_sum = 0.0
        self.candidate_sum = 0.0
        self.absolute_difference_sum = 0.0
        self.squared_difference_sum = 0.0
        self.maximum_absolute_difference = 0.0
        self.central_positive_count = 0
        self.candidate_positive_count = 0
        self.active_count = 0
        self.x_sum = 0.0
        self.y_sum = 0.0
        self.x2_sum = 0.0
        self.y2_sum = 0.0
        self.xy_sum = 0.0
        self.bitwise_equal = True
        self.candidate_nonfinite_count = 0
        self.candidate_negative_count = 0

    def add(self, central: np.ndarray, candidate: np.ndarray) -> None:
        if central.shape != candidate.shape:
            raise ValueError("candidate field shape does not match central")
        if not np.all(np.isfinite(central)) or np.any(central < 0):
            raise ValueError("central comparison field is non-finite or negative")
        self.candidate_nonfinite_count += int(np.count_nonzero(~np.isfinite(candidate)))
        self.candidate_negative_count += int(
            np.count_nonzero(np.isfinite(candidate) & (candidate < 0))
        )
        valid = np.isfinite(candidate) & (candidate >= 0)
        difference = candidate[valid] - central[valid]
        absolute = np.abs(difference)
        self.count += int(valid.sum())
        self.central_sum += float(central[valid].sum())
        self.candidate_sum += float(candidate[valid].sum())
        self.absolute_difference_sum += float(absolute.sum())
        self.squared_difference_sum += float(np.square(difference).sum())
        self.maximum_absolute_difference = max(
            self.maximum_absolute_difference,
            float(absolute.max(initial=0.0)),
        )
        self.central_positive_count += int(np.count_nonzero(central[valid] > 0))
        self.candidate_positive_count += int(np.count_nonzero(candidate[valid] > 0))
        active = valid & ((central > 0) | (candidate > 0))
        x = central[active]
        y = candidate[active]
        self.active_count += x.size
        self.x_sum += float(x.sum())
        self.y_sum += float(y.sum())
        self.x2_sum += float(np.square(x).sum())
        self.y2_sum += float(np.square(y).sum())
        self.xy_sum += float(np.dot(x, y))
        self.bitwise_equal = self.bitwise_equal and np.array_equal(central, candidate)

    def result(self) -> dict[str, Any]:
        denominator = self.central_sum
        correlation_denominator = math.sqrt(
            max(
                self.active_count * self.x2_sum - self.x_sum**2,
                0.0,
            )
            * max(
                self.active_count * self.y2_sum - self.y_sum**2,
                0.0,
            )
        )
        correlation = (
            (
                self.active_count * self.xy_sum - self.x_sum * self.y_sum
            )
            / correlation_denominator
            if correlation_denominator > 0
            else (1.0 if self.bitwise_equal else 0.0)
        )
        return {
            "status": (
                "invalid"
                if self.candidate_nonfinite_count or self.candidate_negative_count
                else "valid"
            ),
            "candidate_nonfinite_count": self.candidate_nonfinite_count,
            "candidate_negative_count": self.candidate_negative_count,
            "metrics_exclude_invalid_candidate_values": bool(
                self.candidate_nonfinite_count or self.candidate_negative_count
            ),
            "cell_value_count": self.count,
            "active_union_count": self.active_count,
            "central_positive_count": self.central_positive_count,
            "candidate_positive_count": self.candidate_positive_count,
            "central_sum": self.central_sum,
            "candidate_sum": self.candidate_sum,
            "signed_normalized_sum_difference": (
                (self.candidate_sum - self.central_sum) / denominator
                if denominator > 0
                else None
            ),
            "normalized_l1_difference": (
                self.absolute_difference_sum / denominator
                if denominator > 0
                else None
            ),
            "root_mean_square_difference": (
                math.sqrt(self.squared_difference_sum / self.count)
                if self.count
                else None
            ),
            "maximum_absolute_difference": self.maximum_absolute_difference,
            "active_union_pearson_correlation": correlation,
            "bitwise_equal": self.bitwise_equal,
        }


def _cell_areas(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    dy = float(np.diff(latitude)[0])
    dx = float(np.diff(longitude)[0])
    geod = Geod(ellps="WGS84")
    output = np.empty((latitude.size, longitude.size), dtype=np.float64)
    for j, lat in enumerate(latitude):
        for i, lon in enumerate(longitude):
            area, _ = geod.polygon_area_perimeter(
                [
                    lon - dx / 2,
                    lon + dx / 2,
                    lon + dx / 2,
                    lon - dx / 2,
                ],
                [
                    lat - dy / 2,
                    lat - dy / 2,
                    lat + dy / 2,
                    lat + dy / 2,
                ],
            )
            output[j, i] = abs(area)
    return output


def _integrate_deposition(path: Path) -> dict[str, float]:
    with netCDF4.Dataset(path) as dataset:
        latitude = _array(dataset.variables["latitude"])
        longitude = _array(dataset.variables["longitude"])
        areas = _cell_areas(latitude, longitude)
        output: dict[str, float] = {}
        for label, variable_name in (
            ("wet_deposition_kg", "WD_spec001"),
            ("dry_deposition_kg", "DD_spec001"),
        ):
            values = _array(dataset.variables[variable_name])
            if not np.all(np.isfinite(values)) or np.any(values < 0):
                raise ValueError(f"invalid deposition values in {path}")
            if values.ndim != 5:
                raise ValueError(f"unexpected deposition dimensions in {path}")
            final_cumulative = values[:, :, -1, :, :]
            output[label] = float((final_cumulative * areas).sum() * 1e-12)
        return output


def _candidate_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "complete":
        raise ValueError(f"candidate is incomplete: {path}")
    return {
        "payload": payload,
        "source": {
            "path": manifest_path.as_posix(),
            "size_bytes": manifest_path.stat().st_size,
            "sha256": _sha256(manifest_path),
        },
    }


def compare(
    *,
    central: Path,
    candidates: dict[str, Path],
    mass_changing: set[str],
    output: Path,
) -> dict[str, Any]:
    central_record = _candidate_manifest(central)
    central_manifest = central_record["payload"]
    comparison_reports: dict[str, Any] = {}
    for label, path in candidates.items():
        print(f"Comparing {label}", flush=True)
        candidate_record = _candidate_manifest(path)
        candidate_manifest = candidate_record["payload"]
        if set(candidate_manifest["transport_days"]) != set(
            central_manifest["transport_days"]
        ):
            raise ValueError(f"{label} does not have the central source-day set")
        accumulators = {field: FieldAccumulator() for field in FIELDS}
        member_reports: list[dict[str, Any]] = []
        for day in sorted(central_manifest["transport_days"]):
            for species in sorted(
                central_manifest["transport_days"][day]["results"]
            ):
                central_path = _output(central, day, species)
                candidate_path = _output(path, day, species)
                member_fields: dict[str, Any] = {}
                with (
                    netCDF4.Dataset(central_path) as central_dataset,
                    netCDF4.Dataset(candidate_path) as candidate_dataset,
                ):
                    for coordinate in ("time", "height", "latitude", "longitude"):
                        if not np.array_equal(
                            central_dataset.variables[coordinate][:],
                            candidate_dataset.variables[coordinate][:],
                        ):
                            raise ValueError(
                                f"{label}/{day}/{species} coordinate mismatch"
                            )
                    for field, variable_name in FIELDS.items():
                        central_values = _array(
                            central_dataset.variables[variable_name]
                        )
                        candidate_values = _array(
                            candidate_dataset.variables[variable_name]
                        )
                        member_accumulator = FieldAccumulator()
                        member_accumulator.add(central_values, candidate_values)
                        member_fields[field] = member_accumulator.result()
                        accumulators[field].add(central_values, candidate_values)
                member_reports.append(
                    {
                        "source_day": day,
                        "species": species,
                        "central_output_sha256": _sha256(central_path),
                        "candidate_output_sha256": _sha256(candidate_path),
                        "fields": member_fields,
                    }
                )
        central_mass = central_manifest["mass_kg_by_species"]
        candidate_mass = candidate_manifest["mass_kg_by_species"]
        mass_equal = all(
            math.isclose(
                float(central_mass[species]),
                float(candidate_mass[species]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            for species in central_mass
        )
        if label not in mass_changing and not mass_equal:
            raise ValueError(f"{label} changed source mass unexpectedly")
        verification_path = path / "verification/candidate-output-verification-v2.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        comparison_reports[label] = {
            "candidate": candidate_record["source"],
            "verification": {
                "path": verification_path.as_posix(),
                "size_bytes": verification_path.stat().st_size,
                "sha256": _sha256(verification_path),
                "status": verification["status"],
            },
            "whole_output_verification_passed": verification["status"] == "passed",
            "mass_change_expected": label in mass_changing,
            "source_mass_equal_to_central": mass_equal,
            "central_mass_kg_by_species": central_mass,
            "candidate_mass_kg_by_species": candidate_mass,
            "source_mass_ratio_to_central": {
                species: float(candidate_mass[species]) / float(central_mass[species])
                for species in central_mass
            },
            "fields": {
                field: accumulator.result()
                for field, accumulator in accumulators.items()
            },
            "members": member_reports,
        }

    deposition_by_species: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "wet_deposition_kg": 0.0,
            "dry_deposition_kg": 0.0,
        }
    )
    deposition_by_day: dict[str, dict[str, Any]] = defaultdict(dict)
    for day in sorted(central_manifest["transport_days"]):
        for species in sorted(central_manifest["transport_days"][day]["results"]):
            integrated = _integrate_deposition(_output(central, day, species))
            deposition_by_day[day][species] = integrated
            for key, value in integrated.items():
                deposition_by_species[species][key] += value
    deposition_summary = {}
    for species, values in deposition_by_species.items():
        released = float(central_manifest["mass_kg_by_species"][species])
        total = values["wet_deposition_kg"] + values["dry_deposition_kg"]
        deposition_summary[species] = {
            **values,
            "total_deposition_kg": total,
            "released_mass_kg": released,
            "deposited_fraction_of_released_mass": total / released,
        }

    bracket_ordered = all(
        float(
            comparison_reports["emission_factors_low"][
                "candidate_mass_kg_by_species"
            ][species]
        )
        < float(central_manifest["mass_kg_by_species"][species])
        < float(
            comparison_reports["emission_factors_high"][
                "candidate_mass_kg_by_species"
            ][species]
        )
        for species in central_manifest["mass_kg_by_species"]
    )
    report = {
        "schema_version": 1,
        "product": "smoke_validation_2026_sensitivity_field_comparison",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "path": "docs/smoke-validation-protocol-2026-v6-sensitivities.md",
            "sha256": _sha256(
                Path("docs/smoke-validation-protocol-2026-v6-sensitivities.md")
            ),
        },
        "central_candidate": central_record["source"],
        "emission_factor_bracket_ordered_for_every_species": bracket_ordered,
        "comparisons": comparison_reports,
        "central_deposition_attribution": {
            "method": (
                "final cumulative deposition field of each independent day-member "
                "* WGS84 geodesic cell area * 1e-12 kg m-2 storage factor"
            ),
            "by_species": dict(sorted(deposition_summary.items())),
            "by_day_and_species": dict(sorted(deposition_by_day.items())),
        },
    }
    _atomic_json(output, report)
    return report | {
        "output_path": output.as_posix(),
        "output_sha256": _sha256(output),
    }


def _labelled_path(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or not label or not raw_path:
        raise argparse.ArgumentTypeError("candidate must be LABEL=PATH")
    return label, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central", type=Path, required=True)
    parser.add_argument(
        "--candidate",
        type=_labelled_path,
        action="append",
        required=True,
    )
    parser.add_argument("--mass-changing", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(
        central=args.central,
        candidates=dict(args.candidate),
        mass_changing=set(args.mass_changing),
        output=args.output,
    )
    print(
        json.dumps(
            {
                "output": report["output_path"],
                "output_sha256": report["output_sha256"],
                "comparison_count": len(report["comparisons"]),
                "emission_factor_bracket_ordered": (
                    report["emission_factor_bracket_ordered_for_every_species"]
                ),
                "central_deposition_by_species": report[
                    "central_deposition_attribution"
                ]["by_species"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
