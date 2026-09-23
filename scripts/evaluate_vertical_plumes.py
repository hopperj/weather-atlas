#!/usr/bin/env python3
"""Evaluate frozen MISR/FLEXPART pairs against W3 acceptance thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.vertical_plume_observations import evaluate_vertical_pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-seed", type=int, default=2026072601)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    arguments = parser.parse_args()
    report = evaluate_vertical_pairs(
        arguments.pairs,
        bootstrap_seed=arguments.bootstrap_seed,
        bootstrap_repetitions=arguments.bootstrap_repetitions,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
