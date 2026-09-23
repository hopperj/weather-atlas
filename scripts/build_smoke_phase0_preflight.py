#!/usr/bin/env python3
"""Build the machine gate that controls opening smoke holdout output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_phase0 import atomic_json, phase0_preflight, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-freeze", type=Path)
    parser.add_argument("--model-release", type=Path)
    parser.add_argument("--protocol-freeze", type=Path)
    parser.add_argument("--sensitivity-matrix-freeze", type=Path)
    parser.add_argument("--reviewer-approval", type=Path)
    parser.add_argument("--vertical-input-readiness", type=Path)
    parser.add_argument("--holdout-output-opened", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = phase0_preflight(
        cohort_freeze_path=args.cohort_freeze,
        model_release_path=args.model_release,
        protocol_freeze_path=args.protocol_freeze,
        sensitivity_matrix_freeze_path=args.sensitivity_matrix_freeze,
        reviewer_approval_path=args.reviewer_approval,
        holdout_output_opened=args.holdout_output_opened,
        vertical_input_readiness_path=args.vertical_input_readiness,
    )
    atomic_json(args.output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "holdout_execution_authorized": report["holdout_execution_authorized"],
                "output": args.output.resolve().as_posix(),
                "output_sha256": sha256(args.output.resolve()),
                "checks": report["checks"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["holdout_execution_authorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
