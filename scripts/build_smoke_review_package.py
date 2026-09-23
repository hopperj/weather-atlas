#!/usr/bin/env python3
"""Build a checksummed W7 evidence package without creating approvals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.scientific_review import build_review_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    arguments = parser.parse_args()
    package = build_review_package(
        output_directory=arguments.output_directory,
        artifacts=arguments.artifact,
        protocol_id=arguments.protocol_id,
        candidate_id=arguments.candidate_id,
    )
    print(json.dumps(package))


if __name__ == "__main__":
    main()
