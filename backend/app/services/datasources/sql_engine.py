"""SQLAlchemy engine for external PostgreSQL, MySQL and SQLite databases (read-only sessions)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from app.services.datasources.base import (
    ColumnInfo,
    QueryEngine,
    QueryFailed,
    QueryResult,
    QueryTimeout,
    TableInfo,
    to_jsonable,
)

DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306}
_TIMEOUT_MARKERS = ("statement timeout", "canceling statement", "max_execution_time", "query execution was interrupted",
                    "interrupted")


def build_url(kind: str, *, host: str | None, port: int | None, database: str | None,
              username: str | None, password: str | None) -> URL:
    if kind == "postgresql":
        return URL.create("postgresql+psycopg", username=username, password=password, host=host,
                          port=port or 5432, database=database)
    if kind == "mysql":
        return URL.create("mysql+pymysql", username=username, password=password, host=host,
                          port=port or 3306, database=database)
    if kind == "sqlite":
        if not database:
            raise QueryFailed("SQLite connections need a database file path")
        return URL.create("sqlite", database=f"file:{database}?mode=ro", query={"uri": "true"})
    raise QueryFailed(f"Unsupported database type: {kind}")


class SQLAlchemyEngine(QueryEngine):
    def __init__(self, kind: str, url: URL, *, schema: str | None = None, timeout_seconds: float = 20.0) -> None:
        self.kind = kind
        self.dialect = {"postgresql": "postgres", "mysql": "mysql", "sqlite": "sqlite"}[kind]
        self.schema = schema
        timeout_ms = int(timeout_seconds * 1000)
        connect_args: dict[str, Any] = {}
        if kind == "postgresql":
            connect_args = {
                "options": f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}",
                "connect_timeout": 10,
            }
        elif kind == "mysql":
            connect_args = {
                "init_command": f"SET SESSION TRANSACTION READ ONLY, SESSION max_execution_time={timeout_ms}",
                "connect_timeout": 10,
                "read_timeout": int(timeout_seconds) + 5,
            }
        elif kind == "sqlite":
            connect_args = {"timeout": 5, "check_same_thread": False}
        self.engine: Engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, pool_size=2,
                                            max_overflow=2) if kind != "sqlite" else create_engine(
            url, connect_args=connect_args)

    def test(self) -> None:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise QueryFailed(_safe_error(exc)) from exc

    def list_tables(self) -> list[TableInfo]:
        try:
            inspector = inspect(self.engine)
            tables: list[TableInfo] = []
            names = inspector.get_table_names(schema=self.schema) + inspector.get_view_names(schema=self.schema)
            for name in sorted(set(names)):
                cols = inspector.get_columns(name, schema=self.schema)
                tables.append(TableInfo(name=name, columns=[ColumnInfo(c["name"], str(c["type"])) for c in cols]))
            return tables
        except SQLAlchemyError as exc:
            raise QueryFailed(_safe_error(exc)) from exc

    def execute(self, sql: str, *, max_rows: int, timeout_seconds: float) -> QueryResult:
        started = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                if self.kind == "sqlite":
                    deadline = started + timeout_seconds
                    raw = conn.connection.driver_connection
                    raw.set_progress_handler(lambda: int(time.perf_counter() > deadline), 10_000)  # type: ignore[union-attr]
                trans = conn.begin()
                try:
                    if self.kind == "postgresql":
                        conn.execute(text("SET TRANSACTION READ ONLY"))
                    result = conn.execute(text(sql))
                    keys = list(result.keys())
                    rows = result.fetchmany(max_rows + 1)
                    cursor_types = [getattr(d, "type_code", None) for d in (result.cursor.description or [])]
                finally:
                    trans.rollback()  # never commit anything
        except (OperationalError, DBAPIError) as exc:
            message = _safe_error(exc)
            if any(marker in message.lower() for marker in _TIMEOUT_MARKERS):
                raise QueryTimeout(f"Query exceeded the {timeout_seconds:.0f}s timeout") from exc
            raise QueryFailed(message) from exc
        except SQLAlchemyError as exc:
            raise QueryFailed(_safe_error(exc)) from exc
        duration = int((time.perf_counter() - started) * 1000)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return QueryResult(
            columns=[{"name": k, "type": str(t or "")} for k, t in zip(keys, cursor_types + [None] * len(keys),
                                                                      strict=False)],
            rows=[[to_jsonable(v) for v in row] for row in rows],
            truncated=truncated,
            duration_ms=duration,
            executed_sql=sql,
        )

    def export_table_parquet(self, table: str, target: str, *, max_rows: int) -> int:
        quoted = self.engine.dialect.identifier_preparer.quote(table)
        if self.schema:
            quoted = f"{self.engine.dialect.identifier_preparer.quote(self.schema)}.{quoted}"
        result = self.execute(f"SELECT * FROM {quoted} LIMIT {int(max_rows)}", max_rows=max_rows,  # noqa: S608
                              timeout_seconds=60)
        names = [c["name"] for c in result.columns]
        table_data = pa.table({n: [row[i] for row in result.rows] for i, n in enumerate(names)})
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table_data, target)
        return result.row_count

    def close(self) -> None:
        self.engine.dispose()


def _safe_error(exc: Exception) -> str:
    """Database errors can echo connection strings; keep only the driver's first message line."""
    orig = getattr(exc, "orig", None)
    text_ = str(orig if orig is not None else exc)
    first = text_.strip().splitlines()[0] if text_.strip() else exc.__class__.__name__
    for marker in ("password", "@"):
        if marker in first.lower() and "authentication" not in first.lower():
            first = first.split(marker)[0]
    return first[:400]
