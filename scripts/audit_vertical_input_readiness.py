#!/usr/bin/env python3
"""Create a W3 assignment template or audit its input-only completeness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_phase0 import atomic_json
from weather_ingest.vertical_input_readiness import (
    audit_vertical_input_readiness,
    build_assignment_template,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vertical-ledger", type=Path, required=True)
    parser.add_argument("--assignment-ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-overpasses", type=int, default=10)
    arguments = parser.parse_args()
    if arguments.assignment_ledger is None:
        vertical = json.loads(arguments.vertical_ledger.read_text())
        payload = build_assignment_template(vertical)
    else:
        payload = audit_vertical_input_readiness(
            vertical_ledger_path=arguments.vertical_ledger,
            assignment_ledger_path=arguments.assignment_ledger,
            minimum_overpasses=arguments.minimum_overpasses,
        )
    atomic_json(arguments.output, payload)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
