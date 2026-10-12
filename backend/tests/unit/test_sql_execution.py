from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb
import pytest

from app.services.datasources.base import QueryFailed, QueryTimeout
from app.services.datasources.duckdb_engine import DuckDBEngine
from app.services.datasources.sql_engine import SQLAlchemyEngine, build_url
from app.services.sql.executor import run_sql
from app.services.sql.validator import Catalog


@pytest.fixture
def duck(tmp_path: Path) -> DuckDBEngine:
    path = tmp_path / "d.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE sales AS SELECT range AS id, range % 5 AS region, range * 1.5 AS revenue FROM range(20000)"
    )
    con.close()
    return DuckDBEngine(path)


def catalog() -> Catalog:
    return Catalog(tables={"sales": {"id": "BIGINT", "region": "BIGINT", "revenue": "DOUBLE"}})


def test_duckdb_engine_read_only_and_no_file_access(duck: DuckDBEngine) -> None:
    with pytest.raises(QueryFailed):
        duck.execute("DELETE FROM sales", max_rows=10, timeout_seconds=5)
    with pytest.raises(QueryFailed):
        duck.execute("SELECT * FROM read_csv('/etc/hosts')", max_rows=10, timeout_seconds=5)
    with pytest.raises(QueryFailed):
        duck.execute("SET enable_external_access = true", max_rows=10, timeout_seconds=5)


def test_truncation_flag(duck: DuckDBEngine) -> None:
    run = run_sql(None, duck, catalog(), "SELECT id FROM sales", max_rows=100)
    assert run.ok and run.result is not None
    assert run.result.row_count == 100 and run.result.truncated


def test_timeout(duck: DuckDBEngine) -> None:
    with pytest.raises(QueryTimeout):
        duck.execute("SELECT count(*) FROM range(10000000000) a", max_rows=1, timeout_seconds=0.3)


def test_blocked_sql_is_recorded(db, duck: DuckDBEngine) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import SQLExecution

    run = run_sql(db, duck, catalog(), "DROP TABLE sales")
    assert run.status == "blocked"
    record = db.get(SQLExecution, run.record_id)
    assert record.status == "blocked" and record.sql_original == "DROP TABLE sales"
    assert duck.execute("SELECT count(*) FROM sales", max_rows=1, timeout_seconds=5).rows == [[20000]]


def test_sqlite_engine_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (a INT)")
    con.execute("INSERT INTO t VALUES (1), (2)")
    con.commit()
    con.close()
    engine = SQLAlchemyEngine(
        "sqlite", build_url("sqlite", host=None, port=None, database=str(path), username=None, password=None)
    )
    assert engine.execute("SELECT SUM(a) FROM t", max_rows=5, timeout_seconds=5).rows == [[3]]
    with pytest.raises(QueryFailed):
        engine.execute("INSERT INTO t VALUES (3)", max_rows=5, timeout_seconds=5)
    assert engine.execute("SELECT COUNT(*) FROM t", max_rows=5, timeout_seconds=5).rows == [[2]]
    assert [t.name for t in engine.list_tables()] == ["t"]


@pytest.mark.postgres
def test_postgres_engine_read_only_and_timeout(settings) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    admin = create_engine(settings.database_url)
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS ro_test CASCADE"))
        conn.execute(text("CREATE SCHEMA ro_test"))
        conn.execute(text("CREATE TABLE ro_test.orders (id int, amount numeric)"))
        conn.execute(text("INSERT INTO ro_test.orders VALUES (1, 10.5), (2, 20)"))
    url = make_url(settings.database_url)
    engine = SQLAlchemyEngine(
        "postgresql",
        build_url(
            "postgresql",
            host=url.host,
            port=url.port,
            database=url.database,
            username=url.username,
            password=url.password,
        ),
        schema="ro_test",
        timeout_seconds=1,
    )
    try:
        assert engine.execute("SELECT SUM(amount) FROM ro_test.orders", max_rows=5, timeout_seconds=1).rows == [[30.5]]
        with pytest.raises(QueryFailed, match="read-only"):
            engine.execute("DELETE FROM ro_test.orders", max_rows=5, timeout_seconds=1)
        with pytest.raises(QueryTimeout):
            engine.execute("SELECT pg_sleep(3)", max_rows=1, timeout_seconds=1)
        assert {t.name for t in engine.list_tables()} == {"orders"}
    finally:
        engine.close()
        with admin.begin() as conn:
            conn.execute(text("DROP SCHEMA ro_test CASCADE"))


def test_concurrent_engines_on_one_dataset_stay_locked_down(tmp_path: Path) -> None:
    """DuckDB shares the database instance per file; a second engine must not crash and must stay hardened."""
    path = tmp_path / "shared.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t AS SELECT 1 AS x")
    con.close()
    first = DuckDBEngine(path)
    second = DuckDBEngine(path)  # configuration already locked by the first engine
    assert second.execute("SELECT x FROM t", max_rows=5, timeout_seconds=5).rows == [[1]]
    with pytest.raises(QueryFailed):
        second.execute("SELECT * FROM read_csv('/etc/hosts')", max_rows=5, timeout_seconds=5)
    first.close()
    second.close()
