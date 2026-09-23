from pathlib import Path


def test_validation_dag_has_preflight_and_never_unlocks_production() -> None:
    source = (Path(__file__).parents[1] / "dags" / "flexpart_smoke_validation.py").read_text()
    assert 'dag_id="flexpart_smoke_validation"' in source
    assert "validation_environment_preflight" in source
    assert "preflight_validation" in source
    assert "enqueue_validation(preflight_validation())" in source
    assert "SIMULATION_WRITES_ENABLED=true" not in source
    assert 'run_kind="validation"' in source
    assert "SMOKE_VALIDATION_RELEASE_MANIFEST" in source
    assert "SMOKE_VALIDATION_CRON" in source
    assert "schedule=_schedule()" in source
