"""Coverage-attributed W2 evaluation over frozen sparse GFAS support."""

from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import netCDF4

from weather_ingest.smoke_evaluation import EvaluationPair, calculate_metrics
from weather_ingest.smoke_validation_contracts import (
    PairRecord,
    clustered_bootstrap_metrics,
    sha256,
)

SupportKey = tuple[str, int, int]


def load_support(
    path: Path,
) -> tuple[dict[SupportKey, str], dict[SupportKey, str], set[SupportKey]]:
    with netCDF4.Dataset(path) as dataset:
        dates = [str(value) for value in dataset.variables["date"][:].tolist()]
        event_ids = [str(value) for value in dataset.variables["event_id"][:].tolist()]
        support_set = dataset.variables["support_set"][:]
        date_indices = dataset.variables["date_index"][:]
        event_indices = dataset.variables["event_index"][:]
        rows = dataset.variables["row"][:]
        columns = dataset.variables["column"][:]
        exact: dict[SupportKey, str] = {}
        dilated: dict[SupportKey, str] = {}
        ambiguous: set[SupportKey] = set()
        for index in range(len(support_set)):
            key = (
                dates[int(date_indices[index])],
                int(rows[index]),
                int(columns[index]),
            )
            role = int(support_set[index])
            if role == 0:
                exact[key] = event_ids[int(event_indices[index])]
            elif role == 1:
                dilated[key] = event_ids[int(event_indices[index])]
            elif role == 2:
                ambiguous.add(key)
            else:
                raise ValueError(f"unexpected support-set flag: {role}")
    if set(exact).intersection(ambiguous):
        raise ValueError("exact and ambiguous support records overlap")
    return exact, dilated, ambiguous


def _read_pairs(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {
            "observed",
            "modelled",
            "date",
            "grid_row",
            "grid_column",
            "species",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"domain pair file lacks W2 fields: {path}")
        for line_number, row in enumerate(reader, start=2):
            observed = float(row["observed"])
            modelled = float(row["modelled"])
            if not math.isfinite(observed) or not math.isfinite(modelled):
                raise ValueError(f"non-finite W2 pair on line {line_number}")
            rows.append(
                {
                    **row,
                    "observed": observed,
                    "modelled": modelled,
                    "grid_row": int(row["grid_row"]),
                    "grid_column": int(row["grid_column"]),
                }
            )
    if not rows:
        raise ValueError(f"domain pair file contains no pairs: {path}")
    return rows


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError(f"support selection produced no rows for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "pair_count": len(rows),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    return calculate_metrics(
        [
            EvaluationPair(
                observed=float(row["observed"]),
                modelled=float(row["modelled"]),
            )
            for row in rows
        ]
    )


def _criteria(metrics: dict[str, float | int | None]) -> dict[str, bool]:
    normalized_bias = metrics["normalized_mean_bias"]
    return {
        "pair_count": int(metrics["pair_count"]) >= 20,
        "normalized_mean_bias": (
            normalized_bias is not None and -0.75 <= float(normalized_bias) <= 2.0
        ),
        "pearson_correlation": float(metrics["pearson_correlation"]) >= 0.30,
        "fraction_within_factor_two": (float(metrics["fraction_within_factor_two"]) >= 0.25),
    }


def _event_bootstrap(
    rows: list[dict[str, Any]],
    *,
    seed: int,
) -> dict[str, Any]:
    pairs = [
        PairRecord(
            pair_id=f"{row['species']}:{row['date']}:{row['grid_row']}:{row['grid_column']}",
            observed=float(row["observed"]),
            modelled=float(row["modelled"]),
            units="kg species per grid-cell day",
            event_id=str(row["support_event_id"]),
            role="primary",
            species=str(row["species"]),
        )
        for row in rows
    ]
    return clustered_bootstrap_metrics(
        pairs,
        replicates=2000,
        seed=seed,
    )


def evaluate_source_attribution(
    *,
    pair_paths: list[Path],
    support_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    exact, dilated, ambiguous = load_support(support_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    species_reports = {}
    event_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"observed": 0.0, "modelled": 0.0}
    )
    event_day_totals: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"observed": 0.0, "modelled": 0.0}
    )
    for pair_path in pair_paths:
        domain_rows = _read_pairs(pair_path)
        species_values = {str(row["species"]) for row in domain_rows}
        if len(species_values) != 1:
            raise ValueError(f"pair file contains multiple species: {pair_path}")
        species = next(iter(species_values))
        exact_rows = []
        dilated_rows = []
        ambiguous_rows = []
        totals = {
            "domain": {"observed": 0.0, "modelled": 0.0},
            "supported": {"observed": 0.0, "modelled": 0.0},
            "ambiguous": {"observed": 0.0, "modelled": 0.0},
        }
        for row in domain_rows:
            key = (row["date"], row["grid_row"], row["grid_column"])
            for name in ("observed", "modelled"):
                totals["domain"][name] += float(row[name])
            if key in exact:
                supported = {
                    **row,
                    "support_event_id": exact[key],
                    "support_role": "exact",
                }
                exact_rows.append(supported)
                for name in ("observed", "modelled"):
                    totals["supported"][name] += float(row[name])
                    event_totals[(species, exact[key])][name] += float(row[name])
                    event_day_totals[(species, exact[key], row["date"])][name] += float(row[name])
            if key in dilated:
                dilated_rows.append(
                    {
                        **row,
                        "support_event_id": dilated[key],
                        "support_role": "dilated",
                    }
                )
            if key in ambiguous:
                ambiguous_rows.append({**row, "support_role": "ambiguous"})
                for name in ("observed", "modelled"):
                    totals["ambiguous"][name] += float(row[name])

        closure = {}
        for name in ("observed", "modelled"):
            outside = totals["domain"][name] - totals["supported"][name] - totals["ambiguous"][name]
            reconstructed = totals["supported"][name] + totals["ambiguous"][name] + outside
            closure[name] = {
                "domain": totals["domain"][name],
                "inside_supported_masks": totals["supported"][name],
                "ambiguous_or_unassigned_masks": totals["ambiguous"][name],
                "outside_supported_masks": outside,
                "reconstructed_domain": reconstructed,
                "closed": math.isclose(
                    reconstructed,
                    totals["domain"][name],
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                ),
            }
        exact_output = _write_rows(
            output_directory / "pairs" / "event-support" / f"{species.lower()}.csv",
            exact_rows,
        )
        dilated_output = _write_rows(
            output_directory / "pairs" / "event-support-dilated" / f"{species.lower()}.csv",
            dilated_rows,
        )
        ambiguous_output = (
            _write_rows(
                output_directory / "pairs" / "ambiguous" / f"{species.lower()}.csv",
                ambiguous_rows,
            )
            if ambiguous_rows
            else None
        )
        domain_metrics = _metrics(domain_rows)
        exact_metrics = _metrics(exact_rows)
        dilated_metrics = _metrics(dilated_rows)
        domain_criteria = _criteria(domain_metrics)
        exact_criteria = _criteria(exact_metrics)
        dilated_criteria = _criteria(dilated_metrics)
        species_reports[species] = {
            "domain_pairs": {
                "path": pair_path.resolve().as_posix(),
                "sha256": sha256(pair_path),
                "pair_count": len(domain_rows),
            },
            "exact_support_pairs": exact_output,
            "dilated_support_pairs": dilated_output,
            "ambiguous_pairs": ambiguous_output,
            "domain_metrics": domain_metrics,
            "exact_support_metrics": exact_metrics,
            "dilated_support_metrics": dilated_metrics,
            "criteria": {
                "domain": domain_criteria,
                "exact_support": exact_criteria,
                "dilated_support": dilated_criteria,
            },
            "criteria_passed": {
                "domain": all(domain_criteria.values()),
                "exact_support": all(exact_criteria.values()),
                "dilated_support": all(dilated_criteria.values()),
            },
            "exact_support_event_bootstrap": _event_bootstrap(
                exact_rows,
                seed=2026072601,
            ),
            "coverage_closure": closure,
        }

    event_total_rows = [
        {
            "species": species,
            "event_id": event_id,
            "observed": values["observed"],
            "modelled": values["modelled"],
        }
        for (species, event_id), values in sorted(event_totals.items())
    ]
    event_totals_output = _write_rows(
        output_directory / "event-totals.csv",
        event_total_rows,
    )
    event_day_rows = [
        {
            "species": species,
            "event_id": event_id,
            "date": day,
            "observed": values["observed"],
            "modelled": values["modelled"],
        }
        for (species, event_id, day), values in sorted(event_day_totals.items())
    ]
    event_day_totals_output = _write_rows(
        output_directory / "event-day-totals.csv",
        event_day_rows,
    )
    return {
        "artifact_type": "w2-gfas-source-attribution",
        "schema_version": 1,
        "status": "complete",
        "support": {
            "path": support_path.resolve().as_posix(),
            "sha256": sha256(support_path),
            "exact_cell_day_count": len(exact),
            "dilated_cell_day_count": len(dilated),
            "ambiguous_cell_day_count": len(ambiguous),
        },
        "species": species_reports,
        "event_totals": event_totals_output,
        "event_day_totals": event_day_totals_output,
        "all_coverage_closures_passed": all(
            closure["closed"]
            for report in species_reports.values()
            for closure in report["coverage_closure"].values()
        ),
        "reviewer_coverage_disposition_required": True,
        "w2_closed": False,
    }
