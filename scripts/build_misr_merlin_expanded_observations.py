#!/usr/bin/env python3
"""Extract expanded MINX observations after height-blind file selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weather_ingest.misr_minx import parse_minx_plume
from weather_ingest.vertical_plume_observations import observation_from_minx

OPERATOR_VERSION = "misr-minx-expanded-blue-wind-corrected-median-agl-v1"
MINIMUM_AGL_M = 250.0
MINIMUM_VALID_RETRIEVALS = 10


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
    parser.add_argument("--observation-ledger", type=Path, required=True)
    parser.add_argument("--extraction-audit", type=Path, required=True)
    args = parser.parse_args()

    blind_path = args.blind_qa_ledger.resolve()
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    if (
        blind.get("artifact_type") != "w3-expanded-height-blind-minx-qa-ledger"
        or blind.get("selection_firewall", {}).get("observed_height_magnitude_accessed")
        is not False
        or blind.get("selection_firewall", {}).get("flexpart_output_accessed") is not False
    ):
        raise ValueError("expanded observations require a valid blind selection ledger")

    observations = []
    records = []
    for record in blind["records"]:
        if record["status"] != "selected_height_blind":
            records.append(
                {
                    "overpass_id": record["overpass_id"],
                    "orbit_overpass_id": record["orbit_overpass_id"],
                    "status": "not_selected_before_height_extraction",
                    "reason": record.get("reason"),
                }
            )
            continue
        selected = record["selected"]
        path = Path(selected["source"]["path"]).resolve()
        if sha256(path) != selected["source"]["sha256"]:
            raise ValueError(f"selected MINX hash mismatch: {record['overpass_id']}")
        plume = parse_minx_plume(path)
        if plume.region_name != selected["region_name"]:
            raise ValueError(f"selected MINX identity changed: {record['overpass_id']}")
        valid_count = int(
            plume.valid_heights_agl_m(
                field="wind_corrected",
                minimum_agl_m=MINIMUM_AGL_M,
            ).size
        )
        base_record = {
            "overpass_id": record["overpass_id"],
            "orbit_overpass_id": record["orbit_overpass_id"],
            "plume_family": record["plume_family"],
            "region_name": plume.region_name,
            "acquired_at": selected["acquired_at"],
            "source_latitude": selected["source_latitude"],
            "source_longitude": selected["source_longitude"],
            "valid_retrieval_count": valid_count,
            "alternative_band_fallback_permitted": False,
            "source": artifact(path),
        }
        if valid_count < MINIMUM_VALID_RETRIEVALS:
            records.append(
                {
                    **base_record,
                    "status": "excluded_post_selection_measurement_invalid",
                    "reason": (
                        "selected band has fewer than the frozen minimum number "
                        "of valid wind-corrected AGL retrievals"
                    ),
                }
            )
            continue
        observation = observation_from_minx(
            plume,
            event_id=record["overpass_id"],
            role="expanded_candidate",
            minimum_agl_m=MINIMUM_AGL_M,
        )
        observation = replace(
            observation,
            overpass_id=record["overpass_id"],
            qa_status=f"{plume.retrieval_quality}; blind-selection-passed",
        )
        observations.append(observation)
        records.append({**base_record, "status": "observation_qualified_candidate"})

    observation_payload = {
        "schema_version": 1,
        "artifact_type": "expanded-vertical-plume-observation-ledger",
        "operator_version": OPERATOR_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "blind_qa_ledger": artifact(blind_path),
        "minimum_agl_m": MINIMUM_AGL_M,
        "minimum_valid_retrievals": MINIMUM_VALID_RETRIEVALS,
        "observation_count": len(observations),
        "observations": [asdict(item) for item in observations],
        "selection_firewall": {
            "band_and_plume_selection_frozen_before_height_extraction": True,
            "alternative_band_fallback_after_height_extraction": False,
            "cffeps_height_accessed": False,
            "flexpart_output_accessed": False,
            "model_performance_accessed": False,
        },
    }
    observation_path = args.observation_ledger.resolve()
    atomic_json(observation_path, observation_payload)
    audit_payload = {
        "schema_version": 1,
        "artifact_type": "w3-expanded-minx-post-selection-extraction-audit",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "operator_version": OPERATOR_VERSION,
        "blind_qa_ledger": artifact(blind_path),
        "observation_ledger": artifact(observation_path),
        "minimum_agl_m": MINIMUM_AGL_M,
        "minimum_valid_retrievals": MINIMUM_VALID_RETRIEVALS,
        "qualified_observation_count": len(observations),
        "excluded_post_selection_measurement_invalid_count": sum(
            item["status"] == "excluded_post_selection_measurement_invalid" for item in records
        ),
        "not_selected_before_height_extraction_count": sum(
            item["status"] == "not_selected_before_height_extraction" for item in records
        ),
        "records": records,
        "holdout_height_values_printed_or_inspected_by_script": False,
    }
    audit_path = args.extraction_audit.resolve()
    atomic_json(audit_path, audit_payload)
    print(
        json.dumps(
            {
                "observation_ledger": artifact(observation_path),
                "extraction_audit": artifact(audit_path),
                "qualified_observation_count": len(observations),
                "excluded_post_selection_measurement_invalid_count": audit_payload[
                    "excluded_post_selection_measurement_invalid_count"
                ],
                "height_values_emitted_to_stdout": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
