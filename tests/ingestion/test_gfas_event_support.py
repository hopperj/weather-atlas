from __future__ import annotations

from weather_ingest.gfas_event_support import (
    GFAS_NI,
    build_support_records,
    gfas_cell,
)


def test_gfas_cell_handles_boundaries_and_longitude_wrap() -> None:
    assert gfas_cell(-180.0, 90.0) == (0, 0)
    assert gfas_cell(180.0, -90.0) == (1799, 0)
    assert gfas_cell(-75.05, 45.05) == (449, 1049)


def _area_event(
    event_id: str,
    longitude: float,
    latitude: float,
    *,
    day: str = "2023-06-01",
) -> dict:
    return {
        "event_id": event_id,
        "daily_area": {"central_daily_increment_ha": {day: 1.0}},
        "support_occurrences": [
            {
                "longitude": longitude,
                "latitude": latitude,
                "burn_date": day,
            }
        ],
    }


def test_support_excludes_ambiguous_exact_claims_from_all_events() -> None:
    report = {
        "events": [
            _area_event("a", -75.01, 45.01),
            _area_event("b", -75.02, 45.02),
        ]
    }
    ledger = {
        "retained_events": [
            {"event_id": "a", "role": "retained"},
            {"event_id": "b", "role": "retained"},
        ],
        "reserve_events": [],
    }
    support = build_support_records(area_report=report, source_ledger=ledger)
    assert support["ambiguous_exact_cell_day_count"] == 1
    assert support["exact_record_count"] == 0


def test_support_builds_exact_and_one_cell_dilation_without_cross_event_leakage() -> None:
    report = {
        "events": [
            _area_event("a", -75.05, 45.05),
            _area_event("b", -120.05, 55.05),
        ]
    }
    ledger = {
        "retained_events": [
            {"event_id": "a", "role": "retained"},
            {"event_id": "b", "role": "retained"},
        ],
        "reserve_events": [],
    }
    support = build_support_records(area_report=report, source_ledger=ledger)
    assert support["exact_record_count"] == 2
    assert support["dilated_record_count"] == 18
    assert all(0 <= record["column"] < GFAS_NI for record in support["dilated"])
