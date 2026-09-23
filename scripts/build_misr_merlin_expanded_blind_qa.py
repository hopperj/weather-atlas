#!/usr/bin/env python3
"""Freeze height-blind MINX selections for every plume family in a MERLIN ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from weather_ingest.minx_blind_qa import (
    blind_quality_checks,
    blind_selection_rank,
    parse_minx_without_heights,
    plume_family_name,
    polygon_area_degrees2,
    source_to_polygon_km,
)

OPERATOR_VERSION = "misr-minx-expanded-height-blind-blue-land-smoke-v1"


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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-raw-retrievals", type=int, default=10)
    parser.add_argument("--maximum-source-polygon-distance-km", type=float, default=5.0)
    args = parser.parse_args()

    vertical_path = args.vertical_ledger.resolve()
    vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
    if vertical.get("artifact_type") != "w1-input-only-misr-merlin-vertical-ledger":
        raise ValueError("input is not a MISR/MERLIN vertical availability ledger")
    if vertical.get("selection_firewall", {}).get("observed_height_used_for_ranking"):
        raise ValueError("expanded QA requires a height-blind availability ledger")

    records: list[dict[str, Any]] = []
    for orbit_record in sorted(vertical["overpasses"], key=lambda item: str(item["overpass_id"])):
        provider_by_name = {str(item["p_name"]): item for item in orbit_record["plumes"]}
        files_by_name = {
            Path(item["path"]).name.removeprefix("Plumes_").removesuffix(".txt"): item
            for item in orbit_record["files"]
        }
        grouped: dict[str, list[str]] = defaultdict(list)
        for region_name in provider_by_name:
            grouped[plume_family_name(region_name)].append(region_name)

        for family_name, region_names in sorted(grouped.items()):
            candidates = []
            parsed_candidates = []
            provider_for_parsed: dict[str, dict[str, Any]] = {}
            for region_name in sorted(region_names):
                provider = provider_by_name[region_name]
                file_record = files_by_name.get(region_name)
                if file_record is None:
                    raise ValueError(f"missing frozen MINX file: {region_name}")
                path = Path(file_record["path"]).resolve()
                if sha256(path) != file_record["sha256"]:
                    raise ValueError(f"MINX checksum mismatch: {region_name}")
                plume = parse_minx_without_heights(path)
                expected_time = datetime.fromisoformat(
                    str(provider["p_date"]).replace("Z", "+00:00")
                )
                checks = blind_quality_checks(
                    plume,
                    expected_orbit=int(str(orbit_record["orbit"]).removeprefix("O")),
                    expected_time=expected_time,
                    expected_region_name=region_name,
                    expected_retrieval_count=int(provider["p_num_hts"]),
                    source_latitude=float(provider["p_src_lat"]),
                    source_longitude=float(provider["p_src_long"]),
                    minimum_raw_retrievals=args.minimum_raw_retrievals,
                    maximum_source_polygon_distance_km=(args.maximum_source_polygon_distance_km),
                )
                passed = all(checks.values())
                candidates.append(
                    {
                        "region_name": region_name,
                        "band": plume.band,
                        "retrieval_quality": plume.retrieval_quality,
                        "provider_successful_retrieval_count": int(provider["p_num_hts"]),
                        "raw_retrieval_count": plume.raw_retrieval_count,
                        "polygon_vertex_count": len(plume.polygon),
                        "polygon_area_degrees2": polygon_area_degrees2(plume.polygon),
                        "source_to_polygon_km": source_to_polygon_km(
                            float(provider["p_src_long"]),
                            float(provider["p_src_lat"]),
                            plume.polygon,
                        ),
                        "checks": checks,
                        "passed_blind_qa": passed,
                        "source": artifact(path),
                    }
                )
                if passed:
                    parsed_candidates.append(plume)
                    provider_for_parsed[plume.region_name] = provider

            selected = (
                min(parsed_candidates, key=blind_selection_rank) if parsed_candidates else None
            )
            selected_provider = provider_for_parsed[selected.region_name] if selected else None
            fire_overpass_id = f"{orbit_record['year']}-{family_name}"
            records.append(
                {
                    "overpass_id": fire_overpass_id,
                    "orbit_overpass_id": orbit_record["overpass_id"],
                    "event_id": "unassigned",
                    "plume_family": family_name,
                    "status": (
                        "selected_height_blind" if selected is not None else "excluded_blind_qa"
                    ),
                    "reason": (
                        None
                        if selected is not None
                        else "no MINX band passed every frozen blind-QA check"
                    ),
                    "candidates": candidates,
                    "selected": (
                        {
                            "region_name": selected.region_name,
                            "band": selected.band,
                            "acquired_at": selected.acquired_at.isoformat().replace("+00:00", "Z"),
                            "source_latitude": float(selected_provider["p_src_lat"]),
                            "source_longitude": float(selected_provider["p_src_long"]),
                            "provider_record_sha256": selected_provider["provider_record_sha256"],
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
        "artifact_type": "w3-expanded-height-blind-minx-qa-ledger",
        "operator_version": OPERATOR_VERSION,
        "analyst_status": (
            "implementation_author_non_independent_blinded_analysis_pending_external_review"
        ),
        "method": {
            "unit": "one band-independent MINX plume family within one orbit",
            "height_columns_parsed": False,
            "flexpart_output_accepted_by_interface": False,
            "quality": ["Good", "Fair"],
            "aerosol_type": "Smoke",
            "geometry_type": "Polygon",
            "minimum_raw_retrievals": args.minimum_raw_retrievals,
            "maximum_provider_source_polygon_distance_km": (
                args.maximum_source_polygon_distance_km
            ),
            "rank_order": [
                "Good before Fair",
                "blue before red for land smoke",
                "more raw retrieval rows",
                "region name",
            ],
            "no_fallback_after_height_extraction": True,
        },
        "sources": {"vertical_ledger": artifact(vertical_path)},
        "provider_orbit_count": len(vertical["overpasses"]),
        "prospective_fire_overpass_count": len(records),
        "selected_count": sum(item["status"] == "selected_height_blind" for item in records),
        "excluded_blind_qa_count": sum(item["status"] == "excluded_blind_qa" for item in records),
        "records": records,
        "selection_firewall": {
            "provider_height_summary_used": False,
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
                "provider_orbit_count": payload["provider_orbit_count"],
                "prospective_fire_overpass_count": payload["prospective_fire_overpass_count"],
                "selected_count": payload["selected_count"],
                "excluded_blind_qa_count": payload["excluded_blind_qa_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
