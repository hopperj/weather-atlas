#!/usr/bin/env python3
"""Finalize W1 technical cohort artifacts after immutable GFAS acquisition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_phase0 import (
    atomic_json,
    finalize_w1_source_gfas,
    sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-candidate-ledger", type=Path, required=True)
    parser.add_argument("--gfas-manifest", type=Path, required=True)
    parser.add_argument("--historical-gfs-ledger", type=Path, required=True)
    parser.add_argument("--vertical-ledger", type=Path, required=True)
    parser.add_argument("--surface-ledger", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    finalized, completeness, cohort_freeze = finalize_w1_source_gfas(
        source_candidate_ledger_path=args.source_candidate_ledger.resolve(),
        gfas_manifest_path=args.gfas_manifest.resolve(),
        historical_gfs_ledger_path=args.historical_gfs_ledger.resolve(),
        vertical_ledger_path=args.vertical_ledger.resolve(),
        surface_ledger_path=args.surface_ledger.resolve(),
    )
    output_directory = args.output_directory.resolve()
    outputs = {
        "source_gfas_ledger": output_directory / "source-gfas-ledger.json",
        "input_completeness": output_directory / "input-completeness.json",
        "cohort_freeze": output_directory / "cohort-freeze.json",
    }
    atomic_json(outputs["source_gfas_ledger"], finalized)
    atomic_json(outputs["input_completeness"], completeness)
    cohort_freeze["artifacts"]["source_gfas_ledger"] = {
        "path": outputs["source_gfas_ledger"].as_posix(),
        "size_bytes": outputs["source_gfas_ledger"].stat().st_size,
        "sha256": sha256(outputs["source_gfas_ledger"]),
    }
    cohort_freeze["artifacts"]["input_completeness"] = {
        "path": outputs["input_completeness"].as_posix(),
        "size_bytes": outputs["input_completeness"].stat().st_size,
        "sha256": sha256(outputs["input_completeness"]),
    }
    atomic_json(outputs["cohort_freeze"], cohort_freeze)
    print(
        json.dumps(
            {
                "status": cohort_freeze["status"],
                "outputs": {
                    name: {"path": path.as_posix(), "sha256": sha256(path)}
                    for name, path in outputs.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
