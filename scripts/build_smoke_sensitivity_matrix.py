#!/usr/bin/env python3
"""Freeze the W6 sensitivity matrix and exact config differences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_sensitivity_matrix import build_sensitivity_matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-config", type=Path, required=True)
    parser.add_argument("--specification", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    manifest = build_sensitivity_matrix(
        central_config=arguments.central_config,
        matrix_specification=arguments.specification,
        output_directory=arguments.output_directory,
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
