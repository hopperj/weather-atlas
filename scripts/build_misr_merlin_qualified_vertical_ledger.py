#!/usr/bin/env python3
"""Freeze observation-qualified MERLIN plume families for source-input assignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from weather_ingest.minx_blind_qa import plume_family_name


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
    parser.add_argument("--blind-qa-ledger", type=Path, required=True)
    parser.add_argument("--extraction-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    vertical_path = args.vertical_ledger.resolve()
    blind_path = args.blind_qa_ledger.resolve()
    audit_path = args.extraction_audit.resolve()
    vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if blind["sources"]["vertical_ledger"]["sha256"] != sha256(vertical_path):
        raise ValueError("blind ledger does not reference the supplied vertical ledger")
    if audit["blind_qa_ledger"]["sha256"] != sha256(blind_path):
        raise ValueError("extraction audit does not reference the supplied blind ledger")

    qualified = {
        str(item["overpass_id"]): item
        for item in audit["records"]
        if item["status"] == "observation_qualified_candidate"
    }
    blind_records = {str(item["overpass_id"]): item for item in blind["records"]}
    orbit_records = {str(item["overpass_id"]): item for item in vertical["overpasses"]}
    overpasses = []
    for overpass_id, audit_record in sorted(qualified.items()):
        blind_record = blind_records[overpass_id]
        orbit = orbit_records[str(blind_record["orbit_overpass_id"])]
        family = str(blind_record["plume_family"])
        plumes = [
            item for item in orbit["plumes"] if plume_family_name(str(item["p_name"])) == family
        ]
        region_names = {str(item["p_name"]) for item in plumes}
        files = [
            item
            for item in orbit["files"]
            if Path(item["path"]).name.removeprefix("Plumes_").removesuffix(".txt") in region_names
        ]
        if not plumes or len(files) != len(plumes):
            raise ValueError(f"incomplete qualified plume family: {overpass_id}")
        overpasses.append(
            {
                "overpass_id": overpass_id,
                "year": orbit["year"],
                "orbit": orbit["orbit"],
                "acquisition_times": sorted({str(item["p_date"]) for item in plumes}),
                "plume_count": len(plumes),
                "retrieval_point_count": sum(int(item["p_num_hts"]) for item in plumes),
                "biome_ids": sorted({int(item["p_biome_id"]) for item in plumes}),
                "interior_boxes": sorted({str(item["canadian_interior_box"]) for item in plumes}),
                "plumes": sorted(plumes, key=lambda item: str(item["p_name"])),
                "files": sorted(files, key=lambda item: str(item["path"])),
                "observation_qualification": {
                    "selected_region_name": audit_record["region_name"],
                    "valid_retrieval_count": audit_record["valid_retrieval_count"],
                    "minimum_valid_retrievals": audit["minimum_valid_retrievals"],
                    "minimum_agl_m": audit["minimum_agl_m"],
                },
            }
        )

    payload = {
        "artifact_type": "w1-input-only-misr-merlin-vertical-ledger",
        "schema_version": 1,
        "status": "frozen_observation_qualified_source_assignment_candidates",
        "selection_rules": {
            "unit": "one band-independent fire-plume family within a MISR orbit",
            "minimum_valid_wind_corrected_agl_retrievals": audit["minimum_valid_retrievals"],
            "minimum_agl_m": audit["minimum_agl_m"],
            "model_output_or_performance_used_for_selection": False,
        },
        "sources": {
            "expanded_vertical_ledger": artifact(vertical_path),
            "height_blind_qa_ledger": artifact(blind_path),
            "safe_extraction_audit": artifact(audit_path),
        },
        "overpass_count": len(overpasses),
        "overpasses": overpasses,
        "selection_firewall": {
            "flexpart_output_accessed": False,
            "predicted_observed_residual_accessed": False,
            "observed_height_magnitude_used_for_source_assignment": False,
            "measurement_validity_status_used": True,
        },
    }
    output = args.output.resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "qualified_fire_overpass_count": len(overpasses),
                "unique_orbit_count": len({str(item["orbit"]) for item in overpasses}),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
