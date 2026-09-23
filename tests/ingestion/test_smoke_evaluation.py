from __future__ import annotations

from pathlib import Path

from weather_ingest.smoke_evaluation import EvaluationPair, calculate_metrics, evaluate


def test_evaluation_metrics_are_deterministic() -> None:
    metrics = calculate_metrics(
        [
            EvaluationPair(observed=10, modelled=12),
            EvaluationPair(observed=20, modelled=18),
            EvaluationPair(observed=30, modelled=33),
        ]
    )

    assert metrics["pair_count"] == 3
    assert metrics["mean_bias"] == 1
    assert metrics["normalized_mean_absolute_error"] == 7 / 60
    assert metrics["fraction_within_factor_two"] == 1
    assert metrics["pearson_correlation"] > 0.95


def test_preregistered_gfas_report_records_input_checksums(tmp_path) -> None:
    pairs = tmp_path / "pairs.csv"
    rows = ["observed,modelled"]
    rows.extend(f"{value},{value * 1.1}" for value in range(1, 21))
    pairs.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = evaluate(
        "gfas_inventory", pairs, Path("config/smoke/validation.yaml")
    )

    assert report["passed"] is True
    assert report["criteria_passed"] is True
    assert report["counts_toward_acceptance"] is False
    assert report["assessment_role"] == "diagnostic_inventory_intercomparison"
    assert report["reference_source"].startswith("CAMS GFAS")
    assert len(report["pairs_sha256"]) == 64


def test_zero_observation_normalized_metrics_are_undefined() -> None:
    metrics = calculate_metrics(
        [EvaluationPair(observed=0, modelled=1), EvaluationPair(observed=0, modelled=2)]
    )

    assert metrics["normalized_mean_bias"] is None
    assert metrics["normalized_mean_absolute_error"] is None
