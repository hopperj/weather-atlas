#!/usr/bin/env python3
"""Verify human-authored W7 signoffs and open blocking issues."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.scientific_review import validate_reviewer_signoffs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--issue-ledger", type=Path, required=True)
    parser.add_argument("--signoff", type=Path, action="append", default=[])
    parser.add_argument("--stage", choices=("pre_execution", "final"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = validate_reviewer_signoffs(
        package_manifest=arguments.package_manifest,
        issue_ledger=arguments.issue_ledger,
        signoff_paths=arguments.signoff,
        stage=arguments.stage,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 2)


if __name__ == "__main__":
    main()
