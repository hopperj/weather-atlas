#!/usr/bin/env python3
"""Evaluate W4 pairs and deterministic event/station clustered uncertainty."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from weather_ingest.smoke_evaluation import EvaluationPair, calculate_metrics


def _multiway_bootstrap(
    rows: list[dict[str, str]],
    *,
    seed: int,
    repetitions: int,
) -> dict[str, list[float]]:
    random = np.random.default_rng(seed)
    events = sorted({row["event_id"] for row in rows})
    stations = sorted({row["station_id"] for row in rows})
    metrics: dict[str, list[float]] = {
        "normalized_mean_bias": [],
        "normalized_mean_absolute_error": [],
        "pearson_correlation": [],
    }
    for _ in range(repetitions):
        event_weight = {
            value: count
            for value, count in zip(
                *np.unique(random.choice(events, len(events), replace=True), return_counts=True),
                strict=True,
            )
        }
        station_weight = {
            value: count
            for value, count in zip(
                *np.unique(
                    random.choice(stations, len(stations), replace=True),
                    return_counts=True,
                ),
                strict=True,
            )
        }
        sample = [
            EvaluationPair(float(row["observed"]), float(row["modelled"]))
            for row in rows
            for _ in range(
                int(event_weight.get(row["event_id"], 0))
                * int(station_weight.get(row["station_id"], 0))
            )
        ]
        if not sample:
            continue
        current = calculate_metrics(sample)
        for name in metrics:
            value = current[name]
            if value is not None:
                metrics[name].append(float(value))
    return {
        name: [
            float(np.quantile(values, 0.025)),
            float(np.quantile(values, 0.975)),
        ]
        for name, values in metrics.items()
        if values
    }


def _leave_one_group_out(
    rows: list[dict[str, str]],
    *,
    field: str,
) -> list[dict[str, object]]:
    reports = []
    for value in sorted({row[field] for row in rows}):
        retained = [row for row in rows if row[field] != value]
        if not retained:
            continue
        reports.append(
            {
                "excluded": value,
                "retained_pair_count": len(retained),
                "metrics": calculate_metrics(
                    [
                        EvaluationPair(
                            float(row["observed"]),
                            float(row["modelled"]),
                        )
                        for row in retained
                    ]
                ),
            }
        )
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-seed", type=int, default=20260726)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    arguments = parser.parse_args()
    rows = list(csv.DictReader(arguments.pairs.open(newline="", encoding="utf-8")))
    pairs = [EvaluationPair(float(row["observed"]), float(row["modelled"])) for row in rows]
    metrics = calculate_metrics(pairs)
    normalized_bias = metrics["normalized_mean_bias"]
    normalized_absolute_error = metrics["normalized_mean_absolute_error"]
    criteria = {
        "pair_count": metrics["pair_count"] >= 100,
        "normalized_mean_bias": (
            normalized_bias is not None and -0.30 <= float(normalized_bias) <= 0.30
        ),
        "normalized_mean_absolute_error": (
            normalized_absolute_error is not None and float(normalized_absolute_error) <= 0.50
        ),
        "pearson_correlation": float(metrics["pearson_correlation"]) >= 0.40,
    }
    report = {
        "schema_version": 1,
        "evaluation_kind": "naps_surface_pm25",
        "metrics": metrics,
        "criteria": criteria,
        "criteria_passed": all(criteria.values()),
        "clustered_uncertainty_95pct": _multiway_bootstrap(
            rows,
            seed=arguments.bootstrap_seed,
            repetitions=arguments.bootstrap_repetitions,
        ),
        "bootstrap_seed": arguments.bootstrap_seed,
        "bootstrap_repetitions": arguments.bootstrap_repetitions,
        "leave_one_event_out": _leave_one_group_out(rows, field="event_id"),
        "leave_one_station_out": _leave_one_group_out(rows, field="station_id"),
        "zero_floor_pair_count": sum(float(row["observed"]) == 0 for row in rows),
        "event_count": len({row["event_id"] for row in rows}),
        "station_count": len({row["station_id"] for row in rows}),
        "pairs_sha256": hashlib.sha256(arguments.pairs.read_bytes()).hexdigest(),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
