#!/usr/bin/env python3
"""Evaluate frozen W2 domain, exact-support, and dilated GFAS comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.gfas_source_attribution import evaluate_source_attribution
from weather_ingest.smoke_validation_contracts import atomic_json, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", action="append", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    output_directory = args.output_directory.resolve()
    report = evaluate_source_attribution(
        pair_paths=[path.resolve() for path in args.pairs],
        support_path=args.support.resolve(),
        output_directory=output_directory,
    )
    output = output_directory / "evaluation.json"
    atomic_json(output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "species": sorted(report["species"]),
                "all_coverage_closures_passed": report["all_coverage_closures_passed"],
                "output": output.as_posix(),
                "output_sha256": sha256(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
