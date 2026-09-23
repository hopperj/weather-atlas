from weather_ingest.smoke_cycle_assessment import (
    assess_cycle,
    summarize_counted_cycles,
    validation_environment_preflight,
)


def _manifest(index: int = 1) -> dict[str, object]:
    return {
        "cycle_id": f"cycle-{index}",
        "cycle_kind": "counted",
        "logical_date": f"2026-08-0{index}",
        "scheduled_at_utc": f"2026-08-0{index}T09:15:00Z",
        "enqueued_at_utc": f"2026-08-0{index}T09:20:00Z",
        "terminal_at_utc": f"2026-08-0{index}T11:15:00Z",
        "terminal_status": "succeeded",
        "namespace": f"validation/cycle-{index}",
        "simulation_writes_enabled": False,
        "input_verification": {"passed": True},
        "output_verification": {"passed": True},
        "attempts": [{"attempt_id": f"attempt-{index}", "immutable": True}],
        "map_artifacts": [f"map-{index}.tif"],
        "seed_policy_verification": {"passed": True},
        "mass_integrity_verification": {"passed": True},
        "manual_data_substitution_or_result_editing": False,
        "release_id": "reviewed-release-1",
        "transported_real_fires": 1 if index <= 2 else 0,
    }


def test_environment_preflight_never_enables_production() -> None:
    report = validation_environment_preflight(
        {
            "WEATHER_DATABASE_URL": "secret",
            "WEATHER_DATA_ROOT": "/data",
            "WEATHER_CONFIG_ROOT": "/config",
            "SMOKE_VALIDATION_RELEASE_MANIFEST": "/release.json",
            "SMOKE_VALIDATION_CRON": "15 9 * * *",
            "SMOKE_VALIDATION_RUNS_ENABLED": "true",
            "SIMULATION_WRITES_ENABLED": "false",
        }
    )
    assert report["passed"]
    assert "secret" not in str(report)


def test_cycle_and_four_cycle_assessment_are_artifact_derived() -> None:
    assessments = [
        assess_cycle(
            _manifest(index),
            enqueue_tolerance_minutes=15,
            terminal_sla_hours=6,
        )
        for index in range(1, 5)
    ]
    assert all(item["passed"] for item in assessments)
    summary = summarize_counted_cycles(
        assessments,
        announced_logical_dates=[f"2026-08-0{index}" for index in range(1, 5)],
    )
    assert summary["passed"]


def test_four_cycle_summary_rejects_nonconsecutive_announced_dates() -> None:
    assessments = [
        assess_cycle(
            _manifest(index),
            enqueue_tolerance_minutes=15,
            terminal_sla_hours=6,
        )
        for index in range(1, 5)
    ]
    assessments[2]["logical_date"] = "2026-08-05"
    summary = summarize_counted_cycles(
        assessments,
        announced_logical_dates=[
            "2026-08-01",
            "2026-08-02",
            "2026-08-05",
            "2026-08-04",
        ],
    )
    assert not summary["passed"]
    assert not summary["checks"]["logical_dates_are_consecutive_daily_cycles"]
