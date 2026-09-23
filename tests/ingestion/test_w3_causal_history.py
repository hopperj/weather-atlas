from __future__ import annotations

from datetime import UTC, datetime, timedelta

from weather_ingest.w3_causal_history import (
    area_partition,
    ceil_utc_hour,
    latest_available_state,
    released_area_between,
    segment_at,
    segment_boundaries,
    uniform_area_for_interval,
    verify_causality,
)


def test_area_is_clipped_at_overpass_and_not_shifted() -> None:
    overpass = datetime(2023, 6, 2, 18, tzinfo=UTC)
    start = overpass - timedelta(hours=24)
    curve = {"2023-06-01": 24.0, "2023-06-02": 48.0, "2023-06-03": 96.0}

    partition = area_partition(curve, history_start=start, overpass=overpass)

    assert partition["within_history_window_ha"] == 42.0
    assert partition["after_overpass_excluded_ha"] == 108.0
    assert (
        uniform_area_for_interval(
            curve,
            datetime(2023, 6, 2, 17, tzinfo=UTC),
            datetime(2023, 6, 2, 18, tzinfo=UTC),
        )
        == 2.0
    )


def test_state_and_segments_are_strictly_time_causal() -> None:
    start = datetime(2023, 6, 1, 18, 30, tzinfo=UTC)
    end = datetime(2023, 6, 2, 18, 30, tzinfo=UTC)
    first = datetime(2023, 6, 1, 19, 10, tzinfo=UTC)
    records = [
        {"observed_at": first, "distance_km": 1.0, "provider_row_sha256": "a"},
        {
            "observed_at": datetime(2023, 6, 2, 18, 20, tzinfo=UTC),
            "distance_km": 1.0,
            "provider_row_sha256": "b",
        },
    ]

    boundaries = segment_boundaries(
        start=start,
        end=end,
        evidence_times=(record["observed_at"] for record in records),
    )

    assert first in boundaries
    assert latest_available_state(records, start) is None
    assert latest_available_state(records, first)["provider_row_sha256"] == "a"
    segments = [
        {
            "start_utc": "2023-06-01T19:10:00Z",
            "end_utc": "2023-06-01T20:00:00Z",
            "released_area_ha": {"central": 1.0},
            "fire_state": {"observed_at_utc": "2023-06-01T19:10:00Z"},
            "meteorology": {"initialization_time_utc": "2023-06-01T00:00:00Z"},
        }
    ]
    assert all(verify_causality(overpass=end, segments=segments).values())


def test_hourly_cffeps_adapter_does_not_move_subhour_area() -> None:
    segments = [
        {
            "start_utc": "2023-06-01T18:30:00Z",
            "end_utc": "2023-06-01T19:00:00Z",
            "released_area_ha": {"central": 1.0},
            "fire_state": None,
        },
        {
            "start_utc": "2023-06-01T19:00:00Z",
            "end_utc": "2023-06-01T20:00:00Z",
            "released_area_ha": {"central": 4.0},
            "fire_state": {"ffmc": 90.0, "dmc": 40.0, "dc": 300.0},
        },
    ]
    start = datetime(2023, 6, 1, 18, 30, tzinfo=UTC)

    assert ceil_utc_hour(start) == datetime(2023, 6, 1, 19, tzinfo=UTC)
    assert segment_at(segments, datetime(2023, 6, 1, 19, tzinfo=UTC))["fire_state"]["ffmc"] == 90.0
    assert (
        released_area_between(
            segments,
            start=start,
            end=datetime(2023, 6, 1, 20, tzinfo=UTC),
        )
        == 5.0
    )
    assert (
        released_area_between(
            segments,
            start=ceil_utc_hour(start),
            end=datetime(2023, 6, 1, 20, tzinfo=UTC),
        )
        == 4.0
    )
