#!/usr/bin/env python3
"""Fail closed on malformed or unreviewed operational smoke science registries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from weather_ingest.cffeps import PHASES, load_emission_factors


def validate(config_root: Path, *, require_approved: bool) -> dict[str, object]:
    emission_path = config_root / "emission_factors.yaml"
    payload = yaml.safe_load(emission_path.read_text(encoding="utf-8"))
    for member in ("low", "central", "high"):
        load_emission_factors(emission_path, member)
    for species, definition in payload["species"].items():
        for phase in PHASES:
            values = definition["phases"][phase]
            if not values["low"] <= values["central"] <= values["high"]:
                raise ValueError(f"{species}/{phase} uncertainty bounds are not ordered")
    crosswalk = yaml.safe_load((config_root / "fuel_crosswalk.yaml").read_text(encoding="utf-8"))
    if crosswalk.get("fallback") != "reject" or not crosswalk.get("rules"):
        raise ValueError("fuel crosswalk must reject unmapped fuels")
    review_status = payload["review"]["status"]
    if require_approved and review_status != "approved":
        raise ValueError("operational enablement requires an approved emissions registry")
    return {
        "status": "valid",
        "registryVersion": payload["registry_version"],
        "scientificStatus": payload["scientific_status"],
        "reviewStatus": review_status,
        "species": sorted(payload["species"]),
        "phaseCount": len(PHASES),
        "crosswalkVersion": crosswalk["crosswalk_version"],
        "operationallyApproved": review_status == "approved",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-root", type=Path, default=Path("config/smoke")
    )
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.config_root, require_approved=args.require_approved), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
