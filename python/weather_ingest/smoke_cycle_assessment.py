"""Artifact-derived assessment for scheduled validation-only smoke cycles."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cycle timestamps must include a UTC offset")
    return parsed.astimezone(UTC)


def validation_environment_preflight(
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Report only presence/state; never echo secret values."""

    values = os.environ if environment is None else environment
    required = (
        "WEATHER_DATABASE_URL",
        "WEATHER_DATA_ROOT",
        "WEATHER_CONFIG_ROOT",
        "SMOKE_VALIDATION_RELEASE_MANIFEST",
        "SMOKE_VALIDATION_CRON",
    )
    present = {name: bool(values.get(name)) for name in required}
    simulation_writes = values.get("SIMULATION_WRITES_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    validation_enabled = values.get(
        "SMOKE_VALIDATION_RUNS_ENABLED",
        "false",
    ).lower() in {"1", "true", "yes"}
    return {
        "required_environment_present": present,
        "all_required_environment_present": all(present.values()),
        "validation_runs_enabled": validation_enabled,
        "simulation_writes_enabled": simulation_writes,
        "production_writes_disabled": not simulation_writes,
        "passed": (all(present.values()) and validation_enabled and not simulation_writes),
    }


def assess_cycle(
    manifest: dict[str, Any],
    *,
    enqueue_tolerance_minutes: float,
    terminal_sla_hours: float,
) -> dict[str, Any]:
    if "passed" in manifest or "status_override" in manifest:
        raise ValueError("cycle assessment cannot accept a manually entered pass flag")
    scheduled = _time(manifest["scheduled_at_utc"])
    enqueued = _time(manifest["enqueued_at_utc"])
    terminal = _time(manifest["terminal_at_utc"])
    enqueue_delay = (enqueued - scheduled).total_seconds() / 60.0
    terminal_duration = (terminal - scheduled).total_seconds() / 3600.0
    attempts = manifest["attempts"]
    attempt_ids = [item["attempt_id"] for item in attempts]
    checks = {
        "scheduled_enqueue": (0 <= enqueue_delay <= enqueue_tolerance_minutes),
        "terminal_within_sla": (0 <= terminal_duration <= terminal_sla_hours),
        "terminal_success": manifest["terminal_status"] == "succeeded",
        "input_verification": bool(manifest["input_verification"]["passed"]),
        "complete_output_verification": bool(manifest["output_verification"]["passed"]),
        "validation_namespace_only": str(manifest["namespace"]).startswith("validation/"),
        "production_writes_disabled": not bool(manifest["simulation_writes_enabled"]),
        "immutable_unique_attempts": (
            bool(attempt_ids)
            and len(attempt_ids) == len(set(attempt_ids))
            and all(item.get("immutable", False) for item in attempts)
        ),
        "map_artifacts_published": bool(manifest["map_artifacts"]),
        "unique_seed_policy_verified": bool(manifest["seed_policy_verification"]["passed"]),
        "mass_integrity_verified": bool(manifest["mass_integrity_verification"]["passed"]),
        "manual_substitution_or_editing_absent": not bool(
            manifest.get("manual_data_substitution_or_result_editing", False)
        ),
    }
    return {
        "schema_version": 1,
        "artifact_type": "smoke-validation-cycle-assessment",
        "cycle_id": manifest["cycle_id"],
        "cycle_kind": manifest["cycle_kind"],
        "logical_date": manifest["logical_date"],
        "release_id": manifest["release_id"],
        "transported_real_fires": int(manifest["transported_real_fires"]),
        "enqueue_delay_minutes": enqueue_delay,
        "terminal_duration_hours": terminal_duration,
        "checks": checks,
        "passed": all(checks.values()),
    }


def assess_cycle_file(
    path: Path,
    *,
    enqueue_tolerance_minutes: float,
    terminal_sla_hours: float,
) -> dict[str, Any]:
    report = assess_cycle(
        json.loads(path.read_text()),
        enqueue_tolerance_minutes=enqueue_tolerance_minutes,
        terminal_sla_hours=terminal_sla_hours,
    )
    report["source_manifest"] = {
        "path": path.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return report


def summarize_counted_cycles(
    assessments: list[dict[str, Any]],
    *,
    announced_logical_dates: list[str],
) -> dict[str, Any]:
    counted = [item for item in assessments if item["cycle_kind"] == "counted"]
    dates = [item["logical_date"] for item in counted]
    parsed_dates = [date.fromisoformat(value[:10]) for value in dates]
    release_ids = {item["release_id"] for item in counted}
    cycle_ids = [item["cycle_id"] for item in counted]
    consecutive_dates = len(parsed_dates) == 4 and all(
        current == previous + timedelta(days=1)
        for previous, current in zip(parsed_dates, parsed_dates[1:], strict=False)
    )
    checks = {
        "exactly_four_counted_cycles": len(counted) == 4,
        "unique_counted_cycle_ids": len(cycle_ids) == len(set(cycle_ids)),
        "announced_dates_match": dates == announced_logical_dates,
        "logical_dates_are_consecutive_daily_cycles": consecutive_dates,
        "four_cycles_passed": len(counted) == 4 and all(item["passed"] for item in counted),
        "at_least_two_real_fire_cycles": sum(item["transported_real_fires"] > 0 for item in counted)
        >= 2,
        "one_unchanged_reviewed_release": len(release_ids) == 1 and bool(release_ids),
    }
    return {
        "schema_version": 1,
        "artifact_type": "four-cycle-smoke-validation-summary",
        "announced_logical_dates": announced_logical_dates,
        "counted_cycle_ids": [item["cycle_id"] for item in counted],
        "checks": checks,
        "passed": all(checks.values()),
    }
