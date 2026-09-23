from pathlib import Path


def test_starter_dag_uses_airflow_3_task_sdk() -> None:
    dag_source = (Path(__file__).parents[1] / "dags" / "platform_smoke_test.py").read_text()
    assert "from airflow.sdk import dag, task" in dag_source
    assert 'dag_id="platform_smoke_test"' in dag_source

