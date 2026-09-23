from __future__ import annotations

import pytest
from weather_ingest.w3_readiness import build_eligibility_records


def test_status_only_join_requires_all_three_gates() -> None:
    qa = {
        "records": [
            {
                "overpass_id": "O1",
                "event_id": "E1",
                "status": "selected_height_blind",
                "selected": {"source": {"sha256": "source"}},
            },
            {
                "overpass_id": "O2",
                "event_id": "E2",
                "status": "selected_height_blind",
                "selected": {"source": {"sha256": "source2"}},
            },
        ]
    }
    audit = {
        "records": [
            {
                "overpass_id": "O1",
                "status": "observation_frozen",
                "valid_retrieval_count": 12,
            },
            {
                "overpass_id": "O2",
                "status": "excluded_post_selection_measurement_invalid",
                "valid_retrieval_count": 3,
            },
        ]
    }
    history = {
        "records": [
            {
                "overpass_id": "O1",
                "status": "ready_causal_source_history",
                "history": {"sha256": "history"},
            },
            {
                "overpass_id": "O2",
                "status": "ready_causal_source_history",
                "history": {"sha256": "history2"},
            },
        ]
    }
    emissions = {
        "records": [
            {
                "overpass_id": "O1",
                "status": "ready_causal_cffeps_emission_history",
                "emission_bundle": {"sha256": "emission"},
            },
            {
                "overpass_id": "O2",
                "status": "ready_causal_cffeps_emission_history",
                "emission_bundle": {"sha256": "emission2"},
            },
        ]
    }

    records = build_eligibility_records(qa, audit, history, emissions)

    assert [record["eligible"] for record in records] == [True, False]


def test_status_only_join_rejects_mismatched_cohorts() -> None:
    qa = {"records": [{"overpass_id": "O1"}]}
    audit = {"records": [{"overpass_id": "O2"}]}
    history = {"records": [{"overpass_id": "O1"}]}

    with pytest.raises(ValueError, match="same prospective overpasses"):
        build_eligibility_records(qa, audit, history)
