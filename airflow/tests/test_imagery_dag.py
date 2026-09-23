from pathlib import Path


def test_imagery_collection_has_a_bounded_recurring_server_job() -> None:
    source = (Path(__file__).parents[1] / "dags" / "eccc_imagery_ingestion.py").read_text()

    assert 'dag_id="eccc_imagery_ingest"' in source
    assert 'schedule="*/6 * * * *"' in source
    assert "catchup=False" in source
    assert "max_active_runs=1" in source
    assert 'pool="eccc_downloads"' in source
    assert "execution_timeout=timedelta(minutes=15)" in source
    assert "from weather_ingest.imagery import ingest_imagery" in source
    assert '"imagery.json"' in source
