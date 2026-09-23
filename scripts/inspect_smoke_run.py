#!/usr/bin/env python3
"""Read-only checksum verification and summary for an archived smoke run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str, failures: list[str], root: Path) -> None:
    label = path.relative_to(root).as_posix()
    if not path.is_file():
        failures.append(f"missing:{label}")
    elif sha256(path) != expected:
        failures.append(f"checksum_mismatch:{label}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=UUID)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data")),
    )
    args = parser.parse_args()
    root = args.data_root.resolve()
    run_dir = root / "derived/smoke/runs" / str(args.run_id)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"No archived manifest for run {args.run_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    verify(
        run_dir / "input/gfs_manifest.json",
        manifest["gfs_manifest_sha256"],
        failures,
        root,
    )
    verify(
        run_dir / "input/fire_snapshot.json",
        manifest["event_snapshot_sha256"],
        failures,
        root,
    )
    for asset in manifest["assets"]:
        verify(root / asset["relative_path"], asset["sha256"], failures, root)
    for species, result in manifest["transport_results"].items():
        output_dir = run_dir / "transport" / species.lower() / "output"
        for name, expected in result["output_sha256"].items():
            verify(output_dir / name, expected, failures, root)
    summary = {
        "run_id": manifest["run_id"],
        "scenario_config_sha256": manifest["scenario_config_sha256"],
        "species": sorted(manifest["member_manifests"]),
        "mass_kg_by_species": manifest["mass_kg_by_species"],
        "asset_count": len(manifest["assets"]),
        "primary_emissions_only": manifest["primary_emissions_only"],
        "checksum_failures": failures,
        "status": "verified" if not failures else "failed",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
