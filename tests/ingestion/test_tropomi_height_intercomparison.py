from __future__ import annotations

import numpy as np
import pytest
from weather_ingest.tropomi_height_intercomparison import (
    _containing_cell,
    _layer_geometry,
    _mass_weighted_height,
)


def test_layer_geometry_interprets_flexpart_heights_as_upper_boundaries() -> None:
    midpoints, thickness = _layer_geometry(np.asarray([50.0, 100.0, 250.0]))

    assert midpoints.tolist() == [25.0, 75.0, 175.0]
    assert thickness.tolist() == [50.0, 50.0, 150.0]


def test_mass_weighted_height_weights_concentration_by_layer_thickness() -> None:
    height, column_weight = _mass_weighted_height(
        np.asarray([2.0, 1.0]),
        np.asarray([50.0, 150.0]),
    )

    assert column_weight == 200.0
    assert height == pytest.approx(62.5)


def test_zero_column_has_no_defined_model_height() -> None:
    height, column_weight = _mass_weighted_height(
        np.zeros(2), np.asarray([50.0, 150.0])
    )

    assert height is None
    assert column_weight == 0.0


def test_containing_cell_uses_half_open_grid_edges() -> None:
    centres = np.asarray([-140.5, -139.5, -138.5])

    assert _containing_cell(centres, -141.0) == 0
    assert _containing_cell(centres, -140.000001) == 0
    assert _containing_cell(centres, -140.0) == 1
    assert _containing_cell(centres, -138.000001) == 2
    assert _containing_cell(centres, -138.0) is None
