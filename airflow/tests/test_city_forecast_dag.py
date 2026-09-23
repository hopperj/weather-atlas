from pathlib import Path


def test_city_forecast_dag_reconciles_amendments_every_fifteen_minutes() -> None:
    source = (Path(__file__).parents[1] / "dags" / "eccc_city_forecast_ingestion.py").read_text()

    assert 'dag_id="eccc_city_forecasts_ingest"' in source
    assert 'schedule="*/15 * * * *"' in source
    assert 'pool="eccc_downloads"' in source
    assert "ingest_city_forecasts" in source
    assert "max_active_runs=1" in source
