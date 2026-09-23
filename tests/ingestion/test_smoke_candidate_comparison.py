from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


def _module():
    path = Path("scripts/compare_smoke_validation_candidates.py")
    specification = importlib.util.spec_from_file_location("candidate_comparison", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_field_accumulator_reports_exact_and_scaled_fields() -> None:
    accumulator = _module().FieldAccumulator()
    central = np.asarray([0.0, 1.0, 2.0])
    accumulator.add(central, central * 2.0)
    result = accumulator.result()

    assert result["signed_normalized_sum_difference"] == 1.0
    assert result["normalized_l1_difference"] == 1.0
    assert result["active_union_pearson_correlation"] == 1.0
    assert result["bitwise_equal"] is False
