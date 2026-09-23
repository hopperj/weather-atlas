"""Status-only join for blinded W3 observation and causal-input ledgers."""

from __future__ import annotations

from typing import Any


def build_eligibility_records(
    blind_qa: dict[str, Any],
    extraction_audit: dict[str, Any],
    causal_history: dict[str, Any],
    causal_emissions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Join gates without opening the observation ledger or reading heights."""

    qa_by_id = {row["overpass_id"]: row for row in blind_qa["records"]}
    audit_by_id = {row["overpass_id"]: row for row in extraction_audit["records"]}
    history_by_id = {row["overpass_id"]: row for row in causal_history["records"]}
    emissions_by_id = (
        {row["overpass_id"]: row for row in causal_emissions["records"]}
        if causal_emissions is not None
        else None
    )
    identifiers = set(qa_by_id)
    if identifiers != set(audit_by_id) or identifiers != set(history_by_id):
        raise ValueError("W3 ledgers do not contain the same prospective overpasses")
    if emissions_by_id is not None and identifiers != set(emissions_by_id):
        raise ValueError("W3 ledgers do not contain the same prospective overpasses")

    records = []
    for overpass_id in sorted(identifiers):
        qa = qa_by_id[overpass_id]
        audit = audit_by_id[overpass_id]
        history = history_by_id[overpass_id]
        emissions = emissions_by_id[overpass_id] if emissions_by_id is not None else None
        blind_selected = qa["status"] == "selected_height_blind"
        observation_frozen = audit["status"] == "observation_frozen"
        causal_ready = history["status"] == "ready_causal_source_history"
        emissions_ready = (
            emissions is None or emissions["status"] == "ready_causal_cffeps_emission_history"
        )
        eligible = blind_selected and observation_frozen and causal_ready and emissions_ready
        records.append(
            {
                "overpass_id": overpass_id,
                "event_id": qa.get("event_id"),
                "status": (
                    "eligible_blinded_w3_case" if eligible else "excluded_before_model_execution"
                ),
                "eligible": eligible,
                "gates": {
                    "height_blind_file_selection": qa["status"],
                    "post_selection_measurement_validity": audit["status"],
                    "causal_source_history": history["status"],
                    "causal_cffeps_emission_history": (
                        emissions["status"] if emissions is not None else "not_supplied"
                    ),
                },
                "valid_misr_retrieval_count": audit.get("valid_retrieval_count"),
                "selected_source_sha256": (
                    (qa.get("selected") or {}).get("source", {}).get("sha256")
                ),
                "causal_history_sha256": (history.get("history", {}).get("sha256")),
                "causal_emission_bundle_sha256": (
                    emissions.get("emission_bundle", {}).get("sha256")
                    if emissions is not None
                    else None
                ),
            }
        )
    return records
