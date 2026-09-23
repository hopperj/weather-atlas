from pathlib import Path

import pytest
from weather_common.db import Database, SqlFileError, SqlFileLoader


def test_sql_loader_reads_and_caches_a_reviewed_query(tmp_path: Path) -> None:
    query_root = tmp_path / "queries"
    query_path = query_root / "catalogue" / "list_products.sql"
    query_path.parent.mkdir(parents=True)
    query_path.write_text("SELECT code FROM catalogue.product;\n", encoding="utf-8")
    loader = SqlFileLoader(query_root)

    first = loader.load("catalogue/list_products.sql")
    query_path.write_text("SELECT name FROM catalogue.product;\n", encoding="utf-8")

    assert first == "SELECT code FROM catalogue.product;\n"
    assert loader.load("catalogue/list_products.sql") == first

    loader.clear_cache()
    assert loader.load("catalogue/list_products.sql") == "SELECT name FROM catalogue.product;\n"


@pytest.mark.parametrize(
    "query_name",
    ["", "../secret.sql", "/tmp/query.sql", "catalogue/query.txt", "catalogue\\query.sql"],
)
def test_sql_loader_rejects_unsafe_query_names(tmp_path: Path, query_name: str) -> None:
    loader = SqlFileLoader(tmp_path)

    with pytest.raises(SqlFileError):
        loader.load(query_name)


def test_sql_loader_rejects_missing_and_empty_queries(tmp_path: Path) -> None:
    loader = SqlFileLoader(tmp_path)

    with pytest.raises(SqlFileError, match="does not exist"):
        loader.load("missing.sql")

    (tmp_path / "empty.sql").write_text("  \n", encoding="utf-8")
    with pytest.raises(SqlFileError, match="empty"):
        loader.load("empty.sql")


@pytest.mark.parametrize("min_size,max_size", [(-1, 1), (2, 1), (0, 0)])
def test_database_rejects_invalid_pool_sizes(min_size: int, max_size: int) -> None:
    with pytest.raises(ValueError, match="pool sizes"):
        Database("postgresql://unused", min_size=min_size, max_size=max_size)
