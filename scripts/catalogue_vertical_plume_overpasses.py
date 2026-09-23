#!/usr/bin/env python3
"""Freeze model-blind MISR MINX plume observations and event assignments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.misr_minx import parse_minx_plume
from weather_ingest.vertical_plume_observations import (
    observation_from_minx,
    write_observation_ledger,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minx-root", type=Path, required=True)
    parser.add_argument(
        "--event-assignments",
        type=Path,
        required=True,
        help="JSON mapping MINX region_name to frozen event_id and role",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    assignments = json.loads(arguments.event_assignments.read_text())
    observations = []
    for path in sorted(arguments.minx_root.rglob("Plumes_*.txt")):
        plume = parse_minx_plume(path)
        assignment = assignments.get(plume.region_name)
        if assignment is None:
            continue
        observations.append(
            observation_from_minx(
                plume,
                event_id=assignment["event_id"],
                role=assignment.get("role", "holdout"),
            )
        )
    write_observation_ledger(arguments.output, observations)
    print(json.dumps({"output": arguments.output.as_posix(), "count": len(observations)}))


if __name__ == "__main__":
    main()
