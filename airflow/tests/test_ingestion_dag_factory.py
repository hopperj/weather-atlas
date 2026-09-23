from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass
class _FakeTask:
    task_id: str
    pool: str | None
    upstream_task_ids: set[str] = field(default_factory=set)

    def __getitem__(self, _key: str) -> _FakeTask:
        return self

    def __rshift__(self, downstream: _FakeTask) -> _FakeTask:
        downstream.upstream_task_ids.add(self.task_id)
        return downstream


@dataclass
class _FakeDag:
    dag_id: str
    task_dict: dict[str, _FakeTask] = field(default_factory=dict)


def _upstream_tasks(value: Any) -> set[str]:
    if isinstance(value, _FakeTask):
        return {value.task_id}
    if isinstance(value, dict):
        return set().union(*(_upstream_tasks(item) for item in value.values()), set())
    if isinstance(value, (list, tuple)):
        return set().union(*(_upstream_tasks(item) for item in value), set())
    return set()


def _fake_sdk() -> ModuleType:
    sdk = ModuleType("airflow.sdk")
    current_dag: list[_FakeDag | None] = [None]

    class Param:
        def __init__(self, default: Any = None, **schema: Any) -> None:
            self.default = default
            self.schema = schema

    def dag(**dag_options):
        def decorate(function):
            def instantiate():
                fake_dag = _FakeDag(dag_options["dag_id"])
                current_dag[0] = fake_dag
                try:
                    function()
                finally:
                    current_dag[0] = None
                return fake_dag

            return instantiate

        return decorate

    def task(function=None, **task_options):
        def decorate(callable_function):
            fake_dag = current_dag[0]
            assert fake_dag is not None
            fake_task = _FakeTask(callable_function.__name__, task_options.get("pool"))
            fake_dag.task_dict[fake_task.task_id] = fake_task

            class _TaskCallable:
                def __call__(self, *args, **kwargs):
                    fake_task.upstream_task_ids.update(_upstream_tasks((args, kwargs)))
                    return fake_task

                def expand(self, **kwargs):
                    fake_task.upstream_task_ids.update(_upstream_tasks(kwargs))
                    return fake_task

            return _TaskCallable()

        return decorate(function) if function is not None else decorate

    sdk.dag = dag
    sdk.task = task
    sdk.Param = Param
    sdk.get_current_context = lambda: {}
    return sdk


def test_factory_import_creates_supported_grib_dags_with_expected_dependencies(
    monkeypatch,
) -> None:
    airflow_module = ModuleType("airflow")
    sdk_module = _fake_sdk()
    airflow_module.sdk = sdk_module
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk_module)

    source_path = Path(__file__).parents[1] / "dags" / "eccc_ingestion.py"
    spec = importlib.util.spec_from_file_location("test_eccc_ingestion_dags", source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected_ids = {
        "eccc_gdps_ingest",
        "eccc_hrdpa_ingest",
        "eccc_hrdps_ingest",
        "eccc_hrepa_ingest",
        "eccc_raqdps_ingest",
        "eccc_rdpa_ingest",
        "eccc_rdps_ingest",
    }
    assert {definition.dag_id for definition in module.INGESTION_DAG_DEFINITIONS} == expected_ids
    for dag_id in expected_ids:
        generated = getattr(module, dag_id)
        assert set(generated.task_dict) == {
            "discover_and_register",
            "requests_for_mapping",
            "download_source",
            "validate_source",
            "create_cog",
            "finalize_run",
        }
        assert generated.task_dict["download_source"].pool == "eccc_downloads"
        assert generated.task_dict["create_cog"].pool == "cog_transforms"
        assert generated.task_dict["download_source"].upstream_task_ids == {
            "requests_for_mapping"
        }
        assert generated.task_dict["requests_for_mapping"].upstream_task_ids == {
            "discover_and_register"
        }
        assert generated.task_dict["validate_source"].upstream_task_ids == {
            "download_source"
        }
        assert generated.task_dict["create_cog"].upstream_task_ids == {"validate_source"}
        assert generated.task_dict["finalize_run"].upstream_task_ids == {
            "create_cog",
            "discover_and_register",
        }
