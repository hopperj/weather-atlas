"""Small psycopg helpers for reviewed SQL files.

The database layer intentionally does not expose a query builder. Every statement
is loaded from ``database/queries`` and values are bound by psycopg.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class SqlFileError(ValueError):
    """Raised when a query name is unsafe, missing, or not a SQL file."""


class SqlFileLoader:
    """Load immutable application queries from a bounded directory."""

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("WEATHER_SQL_ROOT")
        default_root = Path(__file__).resolve().parents[2] / "database" / "queries"
        self.root = (root or (Path(configured_root) if configured_root else default_root)).resolve()
        self._cache: dict[str, str] = {}

    def load(self, query_name: str) -> str:
        """Return a reviewed SQL file, rejecting absolute paths and traversal."""

        if not query_name or "\\" in query_name:
            raise SqlFileError("query name must be a non-empty POSIX-style relative path")

        relative_path = PurePosixPath(query_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SqlFileError("query name must remain below the SQL query root")
        if relative_path.suffix != ".sql":
            raise SqlFileError("query name must end in .sql")

        cache_key = relative_path.as_posix()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query_path = (self.root / Path(*relative_path.parts)).resolve()
        if not query_path.is_relative_to(self.root):
            raise SqlFileError("resolved query path escaped the SQL query root")
        if not query_path.is_file():
            raise SqlFileError(f"SQL query does not exist: {cache_key}")

        sql = query_path.read_text(encoding="utf-8")
        if not sql.strip():
            raise SqlFileError(f"SQL query is empty: {cache_key}")
        self._cache[cache_key] = sql
        return sql

    def clear_cache(self) -> None:
        """Clear loaded statements, primarily for development and tests."""

        self._cache.clear()


class SqlExecutor:
    """Execute named SQL files on a caller-owned transaction connection."""

    def __init__(self, connection: AsyncConnection[Any], loader: SqlFileLoader) -> None:
        self.connection = connection
        self.loader = loader

    async def fetch_all(
        self,
        query_name: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = await self.connection.execute(self.loader.load(query_name), parameters)
        return list(await cursor.fetchall())

    async def fetch_one(
        self,
        query_name: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        cursor = await self.connection.execute(self.loader.load(query_name), parameters)
        return await cursor.fetchone()

    async def execute(
        self,
        query_name: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> int:
        cursor = await self.connection.execute(self.loader.load(query_name), parameters)
        return cursor.rowcount


class Database:
    """Own an async connection pool while keeping transaction boundaries explicit."""

    def __init__(
        self,
        connection_url: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        loader: SqlFileLoader | None = None,
    ) -> None:
        if min_size < 0 or max_size < 1 or min_size > max_size:
            raise ValueError("database pool sizes must satisfy 0 <= min_size <= max_size")
        self.loader = loader or SqlFileLoader()
        self.pool = AsyncConnectionPool(
            conninfo=connection_url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"autocommit": False, "row_factory": dict_row},
            check=AsyncConnectionPool.check_connection,
        )

    async def open(self) -> None:
        """Open the pool and wait until its minimum connections are ready."""

        await self.pool.open(wait=True)

    async def close(self) -> None:
        """Close all pooled connections."""

        await self.pool.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlExecutor]:
        """Yield an executor inside one explicit database transaction."""

        async with self.pool.connection() as connection, connection.transaction():
            yield SqlExecutor(connection, self.loader)

    async def __aenter__(self) -> Database:
        await self.open()
        return self

    async def __aexit__(self, *_error: object) -> None:
        await self.close()
