#!/usr/bin/env python3
"""Record known Phase-0 scientific-review issues without resolving them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
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
    parser.add_argument("--vertical-assignment", type=Path, required=True)
    parser.add_argument("--vertical-readiness", type=Path, required=True)
    parser.add_argument("--background-exclusions", type=Path, required=True)
    parser.add_argument("--execution-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = {
        "vertical_assignment": artifact(args.vertical_assignment),
        "vertical_readiness": artifact(args.vertical_readiness),
        "background_exclusions": artifact(args.background_exclusions),
        "execution_record": artifact(args.execution_record),
    }
    issues = [
        {
            "issue_id": "PRE-W3-OBSERVATION-QA-001",
            "workstream": "W3",
            "severity": "blocking",
            "status": "open",
            "owner_role": "emissions_plume_science",
            "summary": (
                "Independently freeze the MINX plume, band, source, terrain, "
                "wind-correction, and rejection ledger before model output is opened."
            ),
            "required_disposition": (
                "The emissions/plume reviewer must accept or reject the documented "
                "header-viewing deviation and attest that observation QA was performed "
                "without candidate output. Retire and replace the cohort if the "
                "prospective blind is judged compromised."
            ),
            "evidence": [
                evidence["vertical_assignment"],
                evidence["execution_record"],
            ],
        },
        {
            "issue_id": "PRE-W3-SOURCE-HISTORY-002",
            "workstream": "W3",
            "severity": "blocking",
            "status": "open",
            "owner_role": "emissions_plume_science",
            "summary": (
                "Freeze the causal pre-overpass emission-history operator used to turn "
                "MCD64A1 area, Fire M3 fuel/CFFDRS state, and meteorology into releases."
            ),
            "required_disposition": (
                "Confirm that only information available at or before each overpass is "
                "used, define treatment of MCD64A1 burn dates and uncertainty, define "
                "the spin-up interval and CFFDRS evolution, and verify the runner "
                "against the normalized historical GFS manifests."
            ),
            "evidence": [
                evidence["vertical_assignment"],
                evidence["vertical_readiness"],
                evidence["execution_record"],
            ],
        },
        {
            "issue_id": "PRE-W4-BACKGROUND-QA-001",
            "workstream": "W4",
            "severity": "blocking",
            "status": "open",
            "owner_role": "air_quality_model_evaluation",
            "summary": (
                "Independently review the machine Fire M3 background exclusions and "
                "add maintenance, calibration, and non-wildfire exceptional events."
            ),
            "required_disposition": (
                "The air-quality reviewer must freeze the completed exclusion ledger "
                "without consulting NAPS PM2.5 magnitudes or candidate performance and "
                "attest to station-coordinate-history handling."
            ),
            "evidence": [
                evidence["background_exclusions"],
                evidence["execution_record"],
            ],
        },
    ]
    payload = {
        "schema_version": 1,
        "artifact_type": "scientific-review-issue-ledger",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "issues": issues,
    }
    output = args.output.expanduser().resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "sha256": sha256(output),
                "issue_count": len(issues),
                "open_blocking_issue_ids": [
                    issue["issue_id"] for issue in issues
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
