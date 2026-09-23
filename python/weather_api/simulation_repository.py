"""Handwritten-SQL repository for immutable scenarios and simulation jobs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol
from uuid import UUID

from psycopg_pool import AsyncConnectionPool
from weather_common.db import SqlFileLoader
from weather_ingest.fire_scenarios import SmokeScenarioConfig


class SimulationNotFoundError(LookupError):
    pass


class SimulationQueueCapacityError(RuntimeError):
    pass


class SimulationRepository(Protocol):
    async def list_scenarios(self, limit: int) -> list[dict[str, Any]]: ...
    async def get_scenario(self, scenario_id: UUID) -> dict[str, Any]: ...
    async def list_revisions(self, scenario_id: UUID) -> list[dict[str, Any]]: ...
    async def get_revision(self, scenario_id: UUID, revision_id: UUID) -> dict[str, Any]: ...
    async def get_run(self, run_id: UUID) -> dict[str, Any]: ...
    async def list_artifacts(self, run_id: UUID) -> list[dict[str, Any]]: ...
    async def create_scenario(
        self, name: str, description: str, config: SmokeScenarioConfig
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...
    async def create_revision(
        self, scenario_id: UUID, config: SmokeScenarioConfig
    ) -> dict[str, Any]: ...
    async def create_run(
        self,
        scenario_id: UUID,
        revision_id: UUID,
        run_kind: str,
        maximum_queued_runs: int,
    ) -> tuple[dict[str, Any], bool]: ...
    async def cancel_run(self, run_id: UUID) -> dict[str, Any]: ...


class PostgresSimulationRepository:
    def __init__(self, pool: AsyncConnectionPool, sql: SqlFileLoader) -> None:
        self.pool = pool
        self.sql = sql

    async def _fetch_all(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        async with self.pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(self.sql.load(query), parameters)
            return list(await cursor.fetchall())

    async def _one(self, query: str, parameters: dict[str, Any]) -> dict[str, Any]:
        rows = await self._fetch_all(query, parameters)
        if not rows:
            raise SimulationNotFoundError
        return rows[0]

    async def list_scenarios(self, limit: int) -> list[dict[str, Any]]:
        return await self._fetch_all("simulation/list_scenarios.sql", {"limit": limit})

    async def get_scenario(self, scenario_id: UUID) -> dict[str, Any]:
        return await self._one("simulation/get_scenario.sql", {"scenario_id": scenario_id})

    async def list_revisions(self, scenario_id: UUID) -> list[dict[str, Any]]:
        await self.get_scenario(scenario_id)
        return await self._fetch_all("simulation/list_revisions.sql", {"scenario_id": scenario_id})

    async def get_revision(self, scenario_id: UUID, revision_id: UUID) -> dict[str, Any]:
        return await self._one(
            "simulation/get_revision.sql",
            {"scenario_id": scenario_id, "revision_id": revision_id},
        )

    async def get_run(self, run_id: UUID) -> dict[str, Any]:
        return await self._one("simulation/get_run.sql", {"run_id": run_id})

    async def list_artifacts(self, run_id: UUID) -> list[dict[str, Any]]:
        await self.get_run(run_id)
        return await self._fetch_all("simulation/list_run_artifacts.sql", {"run_id": run_id})

    async def _revision(
        self, connection: Any, scenario_id: UUID, config: SmokeScenarioConfig
    ) -> dict[str, Any]:
        async with connection.cursor() as cursor:
            await cursor.execute(
                self.sql.load("simulation/create_revision.sql"),
                {
                    "scenario_id": scenario_id,
                    "canonical_config": config.canonical_json(),
                    "config_sha256": config.config_sha256,
                },
            )
            row = await cursor.fetchone()
        if row is None:
            raise SimulationNotFoundError
        return row

    async def create_scenario(
        self, name: str, description: str, config: SmokeScenarioConfig
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        async with self.pool.connection() as connection, connection.transaction():
            async with connection.cursor() as cursor:
                await cursor.execute(
                    self.sql.load("simulation/create_scenario.sql"),
                    {"name": name, "description": description, "owner_label": "local"},
                )
                scenario = await cursor.fetchone()
            if scenario is None:
                raise RuntimeError("scenario insert returned no row")
            revision = await self._revision(connection, scenario["id"], config)
            return scenario, revision

    async def create_revision(
        self, scenario_id: UUID, config: SmokeScenarioConfig
    ) -> dict[str, Any]:
        async with self.pool.connection() as connection, connection.transaction():
            return await self._revision(connection, scenario_id, config)

    async def create_run(
        self,
        scenario_id: UUID,
        revision_id: UUID,
        run_kind: str,
        maximum_queued_runs: int,
    ) -> tuple[dict[str, Any], bool]:
        revision = await self.get_revision(scenario_id, revision_id)
        key_payload = f"queue-v1:{revision['config_sha256']}:{run_kind}"
        run_key = hashlib.sha256(key_payload.encode()).hexdigest()
        async with self.pool.connection() as connection, connection.transaction():
            async with connection.cursor() as cursor:
                await cursor.execute(self.sql.load("simulation/lock_queue.sql"))
                await cursor.execute(
                    self.sql.load("simulation/create_run.sql"),
                    {
                        "scenario_revision_id": revision_id,
                        "run_kind": run_kind,
                        "requested_by": "local-api",
                        "run_key": run_key,
                        "random_seed_policy": json.dumps(
                            {
                                "kind": "fixed_per_species",
                                "base_seed": revision["canonical_config"]["random_seed"],
                                "derivation": "base_plus_flexpart_species_number_v1",
                            }
                        ),
                        "maximum_queued_runs": maximum_queued_runs,
                    },
                )
                row = await cursor.fetchone()
            if row is None:
                raise SimulationQueueCapacityError(
                    f"The smoke queue already contains {maximum_queued_runs} pending runs"
                )
            return row, not row["created"]

    async def cancel_run(self, run_id: UUID) -> dict[str, Any]:
        await self._fetch_all("simulation/request_cancellation.sql", {"run_id": run_id})
        return await self.get_run(run_id)
