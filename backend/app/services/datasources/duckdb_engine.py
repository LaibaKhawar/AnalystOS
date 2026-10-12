"""DuckDB engine for uploaded datasets.

The dataset file is opened read-only, external file access is disabled and the configuration is
locked, so even a query that slipped past validation cannot read the filesystem or change settings.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import duckdb

from app.services.datasources.base import (
    ColumnInfo,
    QueryEngine,
    QueryFailed,
    QueryResult,
    QueryTimeout,
    TableInfo,
    to_jsonable,
)
from app.services.ingestion.naming import quote_ident


class DuckDBEngine(QueryEngine):
    dialect = "duckdb"

    def __init__(self, database_path: str | Path, parquet_dir: str | Path | None = None) -> None:
        self.database_path = str(database_path)
        self.parquet_dir = Path(parquet_dir) if parquet_dir else None
        self._con = duckdb.connect(self.database_path, read_only=True)
        self._con.execute("SET enable_external_access = false")
        self._con.execute("SET threads = 2")
        self._con.execute("SET memory_limit = '1GB'")
        self._con.execute("SET lock_configuration = true")
        self._lock = threading.Lock()

    def list_tables(self) -> list[TableInfo]:
        with self._lock:
            names = [
                r[0]
                for r in self._con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY 1"
                ).fetchall()
            ]
            tables = []
            for name in names:
                cols = self._con.execute(f"DESCRIBE {quote_ident(name)}").fetchall()
                count = self._con.execute(f"SELECT count(*) FROM {quote_ident(name)}").fetchone()
                tables.append(
                    TableInfo(
                        name=name,
                        columns=[ColumnInfo(c[0], str(c[1])) for c in cols],
                        row_count=int(count[0]) if count else None,
                    )
                )
            return tables

    def execute(self, sql: str, *, max_rows: int, timeout_seconds: float) -> QueryResult:
        with self._lock:
            timed_out = threading.Event()

            def _interrupt() -> None:
                timed_out.set()
                self._con.interrupt()

            timer = threading.Timer(timeout_seconds, _interrupt)
            started = time.perf_counter()
            timer.start()
            try:
                cursor = self._con.execute(sql)
                description = cursor.description or []
                rows = cursor.fetchmany(max_rows + 1)
            except duckdb.InterruptException as exc:
                raise QueryTimeout(f"Query exceeded the {timeout_seconds:.0f}s timeout") from exc
            except duckdb.Error as exc:
                if timed_out.is_set():
                    raise QueryTimeout(f"Query exceeded the {timeout_seconds:.0f}s timeout") from exc
                raise QueryFailed(_clean_error(exc)) from exc
            finally:
                timer.cancel()
            duration = int((time.perf_counter() - started) * 1000)
            truncated = len(rows) > max_rows
            rows = rows[:max_rows]
            return QueryResult(
                columns=[{"name": d[0], "type": str(d[1])} for d in description],
                rows=[[to_jsonable(v) for v in row] for row in rows],
                truncated=truncated,
                duration_ms=duration,
                executed_sql=sql,
            )

    def export_table_parquet(self, table: str, target: str, *, max_rows: int) -> int:
        if self.parquet_dir:
            source = self.parquet_dir / f"{table}.parquet"
            if source.exists():
                Path(target).write_bytes(source.read_bytes())
                with self._lock:
                    row = self._con.execute(f"SELECT count(*) FROM {quote_ident(table)}").fetchone()
                return int(row[0]) if row else 0
        raise QueryFailed(f"No parquet export found for table {table}")

    def close(self) -> None:
        self._con.close()


def _clean_error(exc: Exception) -> str:
    text = str(exc)
    # Drop DuckDB's multi-line caret diagrams but keep the actionable first lines.
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("^")]
    return " ".join(lines[:3])[:500]
