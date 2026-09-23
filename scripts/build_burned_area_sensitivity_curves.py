#!/usr/bin/env python3
"""Build independently bounded W6 burned-area curves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.burned_area_uncertainty import (
    build_independent_area_curves,
    write_area_curves,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--central-source", default="MCD64A1")
    arguments = parser.parse_args()
    records = json.loads(arguments.records.read_text())
    payload = build_independent_area_curves(
        records["records"] if isinstance(records, dict) else records,
        central_source=arguments.central_source,
    )
    write_area_curves(arguments.output, payload)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
