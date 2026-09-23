from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
from weather_ingest.surface_pm25_intercomparison import (
    _containing_cell,
    _match,
)


def test_match_uses_same_hour_background_and_excludes_source_dates() -> None:
    source_day = date(2026, 5, 5)
    target = datetime(2026, 5, 5, 12, tzinfo=UTC)
    observations = {("station", target): 10.0}
    for offset, value in enumerate(range(1, 9), start=1):
        background_time = target - timedelta(days=offset)
        observations[("station", background_time)] = float(value)
    observations[("station", target - timedelta(days=10, hours=1))] = 1000.0
    model = {
        "source_days": [source_day, date(2026, 5, 4)],
        "model_by_time": {target: np.asarray([[0.5]])},
        "longitude": np.asarray([0.5, 1.5]),
        "latitude": np.asarray([0.5, 1.5]),
    }
    source = {
        "observations": observations,
        "metadata": {
            "station": {
                "station_key": "station",
                "site_name": "Test",
                "network": "AirNow",
                "latitude": 0.5,
                "longitude": 0.5,
            }
        },
    }

    central, sensitivity, rejections = _match(
        source=source,
        model=model,
        background_window_days=14,
        minimum_background_values=7,
        model_minimum=0.01,
    )

    assert rejections == {}
    assert len(central) == len(sensitivity) == 1
    assert float(central[0]["background_pm25_ug_m3"]) == 5.0
    assert float(central[0]["observed"]) == 5.0
    assert central[0]["background_value_count"] == 7


def test_containing_cell_has_half_open_edges() -> None:
    coordinates = np.asarray([0.5, 1.5])

    assert _containing_cell(coordinates, 0.0) == 0
    assert _containing_cell(coordinates, 0.999) == 0
    assert _containing_cell(coordinates, 1.0) == 1
    assert _containing_cell(coordinates, 2.0) is None
