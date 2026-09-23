#!/usr/bin/env python3
"""Audit released, pending, and unaccounted CFFEPS fuel in a candidate manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def audit(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_days: list[dict[str, Any]] = []
    totals = {
        "released_within_window_tonnes": 0.0,
        "pending_after_window_tonnes": 0.0,
        "reported_cumulative_consumed_tonnes": 0.0,
        "unaccounted_tonnes": 0.0,
    }
    for run in payload["cffeps_runs"]:
        balance = run["fuel_mass_balance"]
        released = float(balance["released_within_window_phase_fuel_tonnes"])
        pending = float(balance["final_pending_phase_fuel_tonnes_sum"])
        cumulative = float(balance["reported_cumulative_consumed_fuel_tonnes"])
        unaccounted = max(cumulative - released - pending, 0.0)
        if cumulative <= 0:
            raise ValueError(f"{run['event_day_id']} has no cumulative consumed fuel")
        source_days.append(
            {
                "event_day_id": run["event_day_id"],
                "released_within_window_tonnes": released,
                "pending_after_window_tonnes": pending,
                "reported_cumulative_consumed_tonnes": cumulative,
                "unaccounted_tonnes": unaccounted,
                "released_within_window_fraction": released / cumulative,
                "pending_after_window_fraction": pending / cumulative,
                "released_plus_pending_accounted_fraction": (released + pending)
                / cumulative,
                "unaccounted_fraction": unaccounted / cumulative,
                "hard_gate_passed": bool(balance["passed"]),
            }
        )
        totals["released_within_window_tonnes"] += released
        totals["pending_after_window_tonnes"] += pending
        totals["reported_cumulative_consumed_tonnes"] += cumulative
        totals["unaccounted_tonnes"] += unaccounted
    cumulative_total = totals["reported_cumulative_consumed_tonnes"]
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": {
            "path": manifest_path.resolve().as_posix(),
            "sha256": _sha256(manifest_path),
        },
        "accounting": "released_plus_pending_queue_equals_cumulative_consumption_v1",
        "transport_scope": "released_within_frozen_24_hour_window_only",
        "source_day_count": len(source_days),
        "totals": {
            **totals,
            "released_within_window_fraction": (
                totals["released_within_window_tonnes"] / cumulative_total
            ),
            "pending_after_window_fraction": (
                totals["pending_after_window_tonnes"] / cumulative_total
            ),
            "released_plus_pending_accounted_fraction": (
                totals["released_within_window_tonnes"]
                + totals["pending_after_window_tonnes"]
            )
            / cumulative_total,
            "unaccounted_fraction": totals["unaccounted_tonnes"] / cumulative_total,
        },
        "source_days": source_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.manifest)
    _atomic_json(args.output, report)
    print(
        json.dumps(
            {
                "source_day_count": report["source_day_count"],
                "totals": report["totals"],
                "output": args.output.resolve().as_posix(),
                "output_sha256": _sha256(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
