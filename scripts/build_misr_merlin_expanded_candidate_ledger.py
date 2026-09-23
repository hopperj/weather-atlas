#!/usr/bin/env python3
"""Join expanded MISR QA and causal source-input readiness without model output."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


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


def atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    fieldnames = list(rows[0]) if rows else []
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def read_artifact(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    path = Path(record["path"]).resolve()
    if sha256(path) != record["sha256"]:
        raise ValueError(f"artifact checksum mismatch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-qa-ledger", type=Path, required=True)
    parser.add_argument("--extraction-audit", type=Path, required=True)
    parser.add_argument("--assignment-ledger", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    blind_path = args.blind_qa_ledger.resolve()
    audit_path = args.extraction_audit.resolve()
    assignment_path = args.assignment_ledger.resolve()
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    if audit["blind_qa_ledger"]["sha256"] != sha256(blind_path):
        raise ValueError("extraction audit does not reference the supplied blind ledger")

    audit_records = {str(item["overpass_id"]): item for item in audit["records"]}
    assignments = {str(item["overpass_id"]): item for item in assignment["assignments"]}
    records = []
    csv_rows = []
    for blind_record in blind["records"]:
        overpass_id = str(blind_record["overpass_id"])
        audit_record = audit_records[overpass_id]
        assigned = assignments.get(overpass_id)
        selected = blind_record.get("selected")
        status = "excluded_blind_qa"
        reason = blind_record.get("reason")
        if audit_record["status"] == "excluded_post_selection_measurement_invalid":
            status = "excluded_measurement_invalid"
            reason = audit_record["reason"]
        elif audit_record["status"] == "observation_qualified_candidate":
            if assigned is None:
                raise ValueError(f"qualified observation lacks assignment: {overpass_id}")
            if assigned["status"] == "excluded_input_invalid":
                status = "excluded_independent_area_invalid"
                reason = assigned["exclusion_reason"]
            else:
                status = "source_area_qualified_transport_pending"
                reason = None

        area_payload = (
            read_artifact(assigned["artifacts"]["independent_area"])
            if assigned is not None
            else None
        )
        fuel_payload = (
            read_artifact(assigned["artifacts"]["fuel"])
            if assigned is not None and assigned.get("artifacts", {}).get("fuel")
            else None
        )
        cffdrs_payload = (
            read_artifact(assigned["artifacts"]["cffdrs_state"])
            if assigned is not None and assigned.get("artifacts", {}).get("cffdrs_state")
            else None
        )
        area = area_payload["operator_result"] if area_payload else None
        record = {
            "overpass_id": overpass_id,
            "orbit_overpass_id": blind_record["orbit_overpass_id"],
            "year": int(overpass_id[:4]),
            "status": status,
            "reason": reason,
            "observation": {
                "selected_region_name": (selected["region_name"] if selected is not None else None),
                "selected_band": selected["band"] if selected is not None else None,
                "acquired_at": (selected["acquired_at"] if selected is not None else None),
                "source_latitude": (selected["source_latitude"] if selected is not None else None),
                "source_longitude": (
                    selected["source_longitude"] if selected is not None else None
                ),
                "valid_retrieval_count": audit_record.get("valid_retrieval_count"),
                "selected_source": (selected["source"] if selected is not None else None),
            },
            "source_inputs": {
                "event_id": assigned.get("event_id") if assigned else None,
                "firem3_assigned": assigned is not None and assigned.get("event_id") is not None,
                "independent_area_eligible": bool(area and area["burned_area_eligible"]),
                "central_area_ha": area["central_area_ha"] if area else None,
                "high_confidence_area_ha": (area["high_confidence_area_ha"] if area else None),
                "area_stratum": area["area_stratum"] if area else None,
                "model_fuel": (fuel_payload["model_fuel"] if fuel_payload else None),
                "ffmc": cffdrs_payload["ffmc"] if cffdrs_payload else None,
                "dmc": cffdrs_payload["dmc"] if cffdrs_payload else None,
                "dc": cffdrs_payload["dc"] if cffdrs_payload else None,
                "transport_meteorology_complete": False,
                "causal_cffeps_history_complete": False,
            },
        }
        records.append(record)
        if status == "source_area_qualified_transport_pending":
            csv_rows.append(
                {
                    "overpass_id": overpass_id,
                    "orbit_overpass_id": blind_record["orbit_overpass_id"],
                    "year": int(overpass_id[:4]),
                    "acquired_at_utc": selected["acquired_at"],
                    "source_latitude": selected["source_latitude"],
                    "source_longitude": selected["source_longitude"],
                    "selected_region_name": selected["region_name"],
                    "selected_band": selected["band"],
                    "valid_retrieval_count": audit_record["valid_retrieval_count"],
                    "event_id": assigned["event_id"],
                    "area_stratum": area["area_stratum"],
                    "central_area_ha": area["central_area_ha"],
                    "high_confidence_area_ha": area["high_confidence_area_ha"],
                    "model_fuel": fuel_payload["model_fuel"],
                    "ffmc": cffdrs_payload["ffmc"],
                    "dmc": cffdrs_payload["dmc"],
                    "dc": cffdrs_payload["dc"],
                    "minx_sha256": selected["source"]["sha256"],
                    "transport_status": "pending",
                }
            )

    status_counts = Counter(item["status"] for item in records)
    ready = [
        item for item in records if item["status"] == "source_area_qualified_transport_pending"
    ]
    payload = {
        "schema_version": 1,
        "artifact_type": "w3-expanded-misr-source-readiness-ledger",
        "operator_version": "w3-expanded-misr-source-readiness-status-join-v1",
        "status": "observation_and_source_area_screen_complete_transport_pending",
        "sources": {
            "height_blind_qa": artifact(blind_path),
            "safe_extraction_audit": artifact(audit_path),
            "input_assignment": artifact(assignment_path),
        },
        "criteria": {
            "minimum_agl_m": audit["minimum_agl_m"],
            "minimum_valid_retrievals_per_fire_overpass": audit["minimum_valid_retrievals"],
            "minimum_independent_fire_overpasses_for_w3": 10,
            "firem3_assignment": "complete state/fuel within 5 km and 3 hours",
            "independent_area": "MCD64A1 v061 central area with at least one high-confidence pixel",
        },
        "archive_scope": {
            "requested": "2017-01-01 through 2026-07-27",
            "merlin_records_available": ["2017", "2018"],
            "merlin_zero_record_years": [
                "2019",
                "2020",
                "2021",
                "2022",
                "2023",
                "2024",
                "2025",
                "2026",
            ],
        },
        "prospective_fire_overpass_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "observation_qualified_count": sum(
            item["status"]
            in {
                "excluded_independent_area_invalid",
                "source_area_qualified_transport_pending",
            }
            for item in records
        ),
        "source_area_qualified_count": len(ready),
        "source_area_qualified_unique_orbit_count": len(
            {item["orbit_overpass_id"] for item in ready}
        ),
        "source_area_qualified_by_year": dict(
            sorted(Counter(str(item["year"]) for item in ready).items())
        ),
        "observation_sample_shortfall_resolved": len(ready) >= 10,
        "formal_w3_execution_permitted": False,
        "remaining_gates": [
            "performance-blind central-cohort freeze and clustering rule",
            "historical GFS acquisition for the frozen central cohort",
            "causal source and CFFEPS emission histories",
            "independent plume-science review and protocol refreeze",
        ],
        "records": records,
        "selection_firewall": {
            "flexpart_output_accessed": False,
            "model_performance_accessed": False,
            "provider_height_summary_used_for_file_selection": False,
            "alternative_band_fallback_after_height_extraction": False,
        },
    }
    output_json = args.output_json.resolve()
    output_csv = args.output_csv.resolve()
    atomic_json(output_json, payload)
    atomic_csv(output_csv, csv_rows)
    print(
        json.dumps(
            {
                "output_json": artifact(output_json),
                "output_csv": artifact(output_csv),
                "prospective_fire_overpass_count": len(records),
                "observation_qualified_count": payload["observation_qualified_count"],
                "source_area_qualified_count": len(ready),
                "source_area_qualified_unique_orbit_count": payload[
                    "source_area_qualified_unique_orbit_count"
                ],
                "formal_w3_execution_permitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
