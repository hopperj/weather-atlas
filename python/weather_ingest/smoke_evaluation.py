"""Preregistered, source-agnostic smoke-model evaluation metrics."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(frozen=True, slots=True)
class EvaluationPair:
    observed: float
    modelled: float


def load_evaluation_pairs(path: Path) -> list[EvaluationPair]:
    """Load the stable interchange contract used by GFAS, MISR, and NAPS adapters."""

    rows: list[EvaluationPair] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not {"observed", "modelled"}.issubset(
            reader.fieldnames
        ):
            raise ValueError("evaluation CSV requires observed and modelled columns")
        for index, row in enumerate(reader, start=2):
            try:
                observed = float(row["observed"])
                modelled = float(row["modelled"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid evaluation value on row {index}") from exc
            if not math.isfinite(observed) or not math.isfinite(modelled):
                raise ValueError(f"non-finite evaluation value on row {index}")
            rows.append(EvaluationPair(observed=observed, modelled=modelled))
    if not rows:
        raise ValueError("evaluation CSV contains no pairs")
    return rows


def calculate_metrics(pairs: list[EvaluationPair]) -> dict[str, float | int | None]:
    observed = np.asarray([pair.observed for pair in pairs], dtype=np.float64)
    modelled = np.asarray([pair.modelled for pair in pairs], dtype=np.float64)
    residual = modelled - observed
    mean_observed = float(observed.mean())
    correlation = (
        float(np.corrcoef(observed, modelled)[0, 1])
        if len(pairs) > 1 and observed.std() > 0 and modelled.std() > 0
        else 0.0
    )
    nonzero = observed > 0
    ratios = np.divide(
        modelled[nonzero], observed[nonzero], out=np.zeros(nonzero.sum()), where=True
    )
    observed_sum = float(observed.sum())
    observed_absolute_sum = float(np.abs(observed).sum())
    return {
        "pair_count": len(pairs),
        "factor_two_pair_count": int(nonzero.sum()),
        "mean_observed": mean_observed,
        "mean_modelled": float(modelled.mean()),
        "mean_bias": float(residual.mean()),
        "normalized_mean_bias": (
            float(residual.sum() / observed_sum) if observed_sum != 0 else None
        ),
        "mean_absolute_error": float(np.abs(residual).mean()),
        "normalized_mean_absolute_error": (
            float(np.abs(residual).sum() / observed_absolute_sum)
            if observed_absolute_sum != 0
            else None
        ),
        "root_mean_square_error": float(np.sqrt(np.mean(residual**2))),
        "pearson_correlation": correlation,
        "fraction_within_factor_two": (
            float(np.mean((ratios >= 0.5) & (ratios <= 2.0))) if ratios.size else 0.0
        ),
    }


def _passes(metric: float | int | None, rule: dict[str, Any]) -> bool:
    if metric is None:
        return False
    if "minimum" in rule and metric < float(rule["minimum"]):
        return False
    return not ("maximum" in rule and metric > float(rule["maximum"]))


def evaluate(
    kind: str,
    pairs_path: Path,
    thresholds_path: Path,
    *,
    run_manifest: Path | None = None,
) -> dict[str, Any]:
    """Evaluate one frozen pair set against versioned, preregistered criteria."""

    configuration = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    if (
        configuration.get("schema_version") not in {1, 2}
        or kind not in configuration["evaluations"]
    ):
        raise ValueError(f"unsupported smoke evaluation kind: {kind}")
    definition = configuration["evaluations"][kind]
    metrics = calculate_metrics(load_evaluation_pairs(pairs_path))
    criteria = {
        metric: {
            **rule,
            "actual": metrics[metric],
            "passed": _passes(metrics[metric], rule),
        }
        for metric, rule in definition["criteria"].items()
    }
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    criteria_passed = bool(criteria) and all(rule["passed"] for rule in criteria.values())
    assessment_role = definition.get("assessment_role", "engineering_gate")
    acceptance_capable = bool(definition.get("acceptance_capable", False))
    protocol_path = (
        Path(configuration["protocol_path"]) if configuration.get("protocol_path") else None
    )
    return {
        "schema_version": 1,
        "evaluation_kind": kind,
        "threshold_version": configuration.get("threshold_version"),
        "protocol_id": configuration.get("protocol_id"),
        "protocol_path": protocol_path.as_posix() if protocol_path else None,
        "protocol_sha256": (
            sha256(protocol_path) if protocol_path and protocol_path.is_file() else None
        ),
        "assessment_role": assessment_role,
        "acceptance_capable": acceptance_capable,
        "reference_source": definition["reference_source"],
        "units": definition["units"],
        "pairs_path": pairs_path.as_posix(),
        "pairs_sha256": sha256(pairs_path),
        "thresholds_sha256": sha256(thresholds_path),
        "run_manifest_path": run_manifest.as_posix() if run_manifest else None,
        "run_manifest_sha256": sha256(run_manifest) if run_manifest else None,
        "metrics": metrics,
        "criteria": criteria,
        "criteria_passed": criteria_passed,
        "counts_toward_acceptance": criteria_passed and acceptance_capable,
        # Kept for CLI/backward compatibility. Read criteria_passed and
        # counts_toward_acceptance when interpreting a scientific result.
        "passed": criteria_passed,
    }


def write_evaluation_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
