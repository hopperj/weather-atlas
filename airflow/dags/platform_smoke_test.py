"""Starter DAG proving the Airflow 3 Task SDK and LocalExecutor setup."""

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="platform_smoke_test",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["platform", "smoke-test"],
)
def platform_smoke_test():
    @task
    def confirm_runtime() -> str:
        return "weather platform Airflow runtime is ready"

    confirm_runtime()


platform_smoke_test()

