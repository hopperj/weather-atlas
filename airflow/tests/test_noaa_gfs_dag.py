from pathlib import Path


def _source() -> str:
    return (Path(__file__).parents[1] / "dags" / "noaa_gfs_ingestion.py").read_text()


def test_gfs_dag_is_six_hourly_idempotent_and_pool_constrained() -> None:
    source = _source()

    assert 'dag_id="noaa_gfs_ingest"' in source
    assert 'schedule="15 5,11,17,23 * * *"' in source
    assert "max_active_runs=1" in source
    assert 'pool="noaa_gfs_downloads"' in source
    assert "plan_from_noaa" in source
    assert "download_and_validate_request" in source
    assert "write_cycle_manifests" in source
    assert "download_and_validate.expand(request=requests)" in source

