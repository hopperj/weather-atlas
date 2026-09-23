#!/usr/bin/env python3
"""Evaluate W6 completeness and mass-identity constraints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_sensitivity_matrix import evaluate_sensitivity_matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix-manifest", type=Path, required=True)
    parser.add_argument("--result-manifest", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = evaluate_sensitivity_matrix(
        matrix_manifest=arguments.matrix_manifest,
        result_manifests=arguments.result_manifest,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
