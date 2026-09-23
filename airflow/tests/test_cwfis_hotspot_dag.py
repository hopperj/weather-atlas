from pathlib import Path


def _source() -> str:
    return (
        Path(__file__).parents[1] / "dags" / "cwfis_hotspot_ingestion.py"
    ).read_text()


def test_cwfis_dag_is_daily_idempotent_and_pool_constrained() -> None:
    source = _source()

    assert 'dag_id="nrcan_cwfis_hotspots_ingest"' in source
    assert 'schedule="15 7 * * *"' in source
    assert "max_active_runs=1" in source
    assert 'pool="nrcan_cwfis_downloads"' in source
    assert "plan_from_cwfis" in source
    assert "ingest_request" in source
    assert "publish_latest" in source
    assert "ingest_daily_file.expand(request=requests)" in source
