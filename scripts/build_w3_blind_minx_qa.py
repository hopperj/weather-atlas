#!/usr/bin/env python3
"""Freeze a MINX plume selection ledger without parsing plume-height columns."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from weather_ingest.minx_blind_qa import (
    blind_quality_checks,
    blind_selection_rank,
    parse_minx_without_heights,
    polygon_area_degrees2,
    source_to_polygon_km,
)

OPERATOR_VERSION = "misr-minx-height-blind-blue-land-smoke-v1"


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
    parser.add_argument("--vertical-ledger", type=Path, required=True)
    parser.add_argument("--assignment-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-raw-retrievals", type=int, default=10)
    parser.add_argument("--maximum-source-polygon-distance-km", type=float, default=5.0)
    args = parser.parse_args()

    vertical_path = args.vertical_ledger.resolve()
    assignment_path = args.assignment_ledger.resolve()
    vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    overpasses = {str(item["overpass_id"]): item for item in vertical["overpasses"]}
    assignments = {str(item["overpass_id"]): item for item in assignment["assignments"]}
    if set(overpasses) != set(assignments):
        raise ValueError("vertical and assignment ledgers cover different overpasses")

    records = []
    for overpass_id in sorted(overpasses):
        overpass = overpasses[overpass_id]
        assigned = assignments[overpass_id]
        if assigned["status"] == "excluded_input_invalid":
            records.append(
                {
                    "overpass_id": overpass_id,
                    "event_id": assigned["event_id"],
                    "status": "excluded_pre_observation_input_invalid",
                    "reason": assigned["exclusion_reason"],
                    "candidates": [],
                    "selected": None,
                }
            )
            continue
        fire_path = Path(assigned["fire_assignment"]["path"]).resolve()
        if sha256(fire_path) != assigned["fire_assignment"]["sha256"]:
            raise ValueError(f"fire assignment hash mismatch: {overpass_id}")
        fire = json.loads(fire_path.read_text(encoding="utf-8"))
        allowed_names = set(fire["selected_source"]["plume_region_names"])
        plume_records = {
            str(item["p_name"]): item
            for item in overpass["plumes"]
            if str(item["p_name"]) in allowed_names
        }
        if set(plume_records) != allowed_names:
            raise ValueError(f"source-linked plume names are incomplete: {overpass_id}")
        files_by_name = {
            Path(item["path"]).name.removeprefix("Plumes_").removesuffix(".txt"): item
            for item in overpass["files"]
        }
        candidates = []
        parsed_candidates = []
        for region_name in sorted(allowed_names):
            provider = plume_records[region_name]
            file_record = files_by_name.get(region_name)
            if file_record is None:
                raise ValueError(f"missing frozen MINX file: {region_name}")
            path = Path(file_record["path"]).resolve()
            if sha256(path) != file_record["sha256"]:
                raise ValueError(f"MINX checksum mismatch: {region_name}")
            plume = parse_minx_without_heights(path)
            expected_time = datetime.fromisoformat(str(provider["p_date"]).replace("Z", "+00:00"))
            checks = blind_quality_checks(
                plume,
                expected_orbit=int(str(overpass["orbit"]).removeprefix("O")),
                expected_time=expected_time,
                expected_region_name=region_name,
                expected_retrieval_count=int(provider["p_num_hts"]),
                source_latitude=float(fire["selected_source"]["latitude"]),
                source_longitude=float(fire["selected_source"]["longitude"]),
                minimum_raw_retrievals=args.minimum_raw_retrievals,
                maximum_source_polygon_distance_km=(args.maximum_source_polygon_distance_km),
            )
            passed = all(checks.values())
            candidates.append(
                {
                    "region_name": region_name,
                    "band": plume.band,
                    "retrieval_quality": plume.retrieval_quality,
                    "raw_retrieval_count": plume.raw_retrieval_count,
                    "polygon_vertex_count": len(plume.polygon),
                    "polygon_area_degrees2": polygon_area_degrees2(plume.polygon),
                    "source_to_polygon_km": source_to_polygon_km(
                        float(fire["selected_source"]["longitude"]),
                        float(fire["selected_source"]["latitude"]),
                        plume.polygon,
                    ),
                    "checks": checks,
                    "passed_blind_qa": passed,
                    "source": artifact(path),
                }
            )
            if passed:
                parsed_candidates.append(plume)
        selected = min(parsed_candidates, key=blind_selection_rank) if parsed_candidates else None
        records.append(
            {
                "overpass_id": overpass_id,
                "event_id": assigned["event_id"],
                "status": (
                    "selected_height_blind" if selected is not None else "excluded_blind_qa"
                ),
                "reason": (
                    None
                    if selected is not None
                    else "no source-linked MINX band passed every blind-QA check"
                ),
                "candidates": candidates,
                "selected": (
                    {
                        "region_name": selected.region_name,
                        "band": selected.band,
                        "source": artifact(selected.source_path),
                        "selection_rank": list(blind_selection_rank(selected)),
                    }
                    if selected is not None
                    else None
                ),
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "w3-height-blind-minx-qa-ledger",
        "operator_version": OPERATOR_VERSION,
        "analyst_status": (
            "implementation_author_non_independent_blinded_analysis_pending_external_review"
        ),
        "conflict_disclosure": (
            "The analyst implemented pipeline components and previously displayed one "
            "raw MINX header containing height summaries. No height magnitude or "
            "FLEXPART output was accessed by this operator."
        ),
        "method": {
            "height_columns_parsed": False,
            "flexpart_output_accepted_by_interface": False,
            "allowed_fields": [
                "file checksum",
                "orbit, acquisition time, region and product version",
                "categorical aerosol, geometry and provider retrieval quality",
                "polygon coordinates",
                "retrieval row count, point identity, coordinates and terrain validity",
                "frozen Fire M3 source coordinate",
            ],
            "quality": ["Good", "Fair"],
            "aerosol_type": "Smoke",
            "geometry_type": "Polygon",
            "minimum_raw_retrievals": args.minimum_raw_retrievals,
            "maximum_source_polygon_distance_km": (args.maximum_source_polygon_distance_km),
            "rank_order": [
                "Good before Fair",
                "blue before red for land smoke",
                "more raw retrieval rows",
                "region name",
            ],
            "no_fallback_after_height_extraction": True,
        },
        "sources": {
            "vertical_ledger": artifact(vertical_path),
            "assignment_ledger": artifact(assignment_path),
        },
        "prospective_overpass_count": len(records),
        "selected_count": sum(item["status"] == "selected_height_blind" for item in records),
        "excluded_pre_observation_input_invalid_count": sum(
            item["status"] == "excluded_pre_observation_input_invalid" for item in records
        ),
        "excluded_blind_qa_count": sum(item["status"] == "excluded_blind_qa" for item in records),
        "records": records,
        "selection_firewall": {
            "observed_height_magnitude_accessed": False,
            "cffeps_height_accessed": False,
            "flexpart_output_accessed": False,
            "model_performance_accessed": False,
        },
    }
    output = args.output.resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "selected_count": payload["selected_count"],
                "excluded_pre_observation_input_invalid_count": payload[
                    "excluded_pre_observation_input_invalid_count"
                ],
                "excluded_blind_qa_count": payload["excluded_blind_qa_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
