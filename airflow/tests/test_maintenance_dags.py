from pathlib import Path


def test_maintenance_dags_are_manual_bounded_and_dry_run_first() -> None:
    source = (Path(__file__).parents[1] / "dags" / "weather_maintenance.py").read_text()

    assert 'dag_id="weather_asset_retention"' in source
    assert 'dag_id="weather_integrity_audit"' in source
    assert 'dag_id="weather_cleanup_temporary_files"' in source
    assert source.count("schedule=None") == 3
    assert source.count("max_active_runs=1") == 3
    assert "parse_maintenance_options" in source
    assert "run_asset_retention" in source
