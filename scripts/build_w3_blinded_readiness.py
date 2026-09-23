#!/usr/bin/env python3
"""Freeze status-only W3 eligibility without reading observed height values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weather_ingest.w3_readiness import build_eligibility_records

OPERATOR_VERSION = "w3-blinded-readiness-status-join-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": resolved.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-qa-ledger", type=Path, required=True)
    parser.add_argument("--extraction-audit", type=Path, required=True)
    parser.add_argument("--causal-history-ledger", type=Path, required=True)
    parser.add_argument("--causal-emission-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-overpasses", type=int, default=10)
    args = parser.parse_args()
    if args.minimum_overpasses < 1:
        parser.error("--minimum-overpasses must be positive")

    qa_path = args.blind_qa_ledger.resolve()
    audit_path = args.extraction_audit.resolve()
    history_path = args.causal_history_ledger.resolve()
    emissions_path = args.causal_emission_ledger.resolve()
    blind_qa = json.loads(qa_path.read_text(encoding="utf-8"))
    extraction_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    causal_history = json.loads(history_path.read_text(encoding="utf-8"))
    causal_emissions = json.loads(emissions_path.read_text(encoding="utf-8"))
    if (
        extraction_audit["blind_qa_ledger"]["sha256"] != sha256(qa_path)
        or causal_history["selection_firewall"]["flexpart_output_accessed"]
        or blind_qa["selection_firewall"]["observed_height_magnitude_accessed"]
        or causal_emissions["selection_firewall"]["misr_height_accessed"]
        or causal_emissions["selection_firewall"]["flexpart_output_accessed"]
    ):
        raise ValueError("W3 ledger provenance or selection firewall is invalid")

    records = build_eligibility_records(
        blind_qa,
        extraction_audit,
        causal_history,
        causal_emissions,
    )
    eligible_count = sum(record["eligible"] for record in records)
    sample_complete = eligible_count >= args.minimum_overpasses
    payload = {
        "schema_version": 1,
        "artifact_type": "w3-blinded-preexecution-readiness",
        "operator_version": OPERATOR_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": (
            "blocked_external_independent_review_required"
            if sample_complete
            else "blocked_insufficient_eligible_observations"
        ),
        "formal_execution_permitted": False,
        "all_required_vertical_inputs_complete": sample_complete,
        "minimum_overpasses": args.minimum_overpasses,
        "prospective_overpass_count": len(records),
        "eligible_overpass_count": eligible_count,
        "sample_size_gate_passed": sample_complete,
        "independent_review_gate_passed": False,
        "independence_disclosure": (
            "The same Codex agent implemented and executed these operators and "
            "previously saw one MINX header containing heights. File selection "
            "was subsequently performed by a parser that cannot read height "
            "columns and before post-selection extraction, but this is not an "
            "independent-scientist signoff."
        ),
        "post_hoc_changes_prohibited": [
            "Do not lower the minimum valid-retrieval count for this cohort.",
            "Do not substitute the red-band file after height extraction.",
            "Do not inspect FLEXPART outputs until the remaining gates are frozen.",
        ],
        "sources": {
            "blind_qa_ledger": artifact(qa_path),
            "extraction_audit": artifact(audit_path),
            "causal_history_ledger": artifact(history_path),
            "causal_emission_ledger": artifact(emissions_path),
            "sealed_observation_ledger": extraction_audit["observation_ledger"],
        },
        "records": records,
        "selection_firewall": {
            "observation_ledger_opened_by_join": False,
            "misr_height_values_accessed_by_join": False,
            "flexpart_output_accessed_by_join": False,
            "eligibility_uses_only_status_counts_and_hashes": True,
        },
    }
    output = args.output.resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "eligible_overpass_count": eligible_count,
                "minimum_overpasses": args.minimum_overpasses,
                "sample_size_gate_passed": sample_complete,
                "formal_execution_permitted": False,
                "height_or_flexpart_values_emitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
