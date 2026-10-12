"""Schema introspection + profiling for external databases.

Each table is sampled (bounded) into an in-memory DuckDB so the same profiler and semantic interpreter
used for uploads apply. Exact row counts come from COUNT(*) on the source.
"""

from __future__ import annotations

import duckdb
import pandas as pd
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import DataSource, TableMetadata
from app.services.datasources.base import QueryFailed
from app.services.datasources.sql_engine import SQLAlchemyEngine
from app.services.ingestion.naming import quote_ident
from app.services.ingestion.service import persist_tables
from app.services.ingestion.types import LoadedTable
from app.services.profiling.profiler import profile_table

log = get_logger(__name__)
SAMPLE_ROWS = 50_000
MAX_TABLES = 40


def introspect_source(db: Session, source: DataSource, engine: SQLAlchemyEngine) -> list[TableMetadata]:
    infos = engine.list_tables()
    allowed = {t.lower() for t in source.allowed_tables} if source.allowed_tables else None
    infos = [t for t in infos if allowed is None or t.name.lower() in allowed][:MAX_TABLES]
    for table in list(source.tables):
        db.delete(table)
    db.flush()
    preparer = engine.engine.dialect.identifier_preparer
    loaded: list[LoadedTable] = []
    profiles = []
    con = duckdb.connect()
    try:
        for info in infos:
            qualified = preparer.quote(info.name)
            if source.db_schema:
                qualified = f"{preparer.quote(source.db_schema)}.{qualified}"
            try:
                count = engine.execute(f"SELECT COUNT(*) FROM {qualified}", max_rows=1, timeout_seconds=30)
                sample = engine.execute(
                    f"SELECT * FROM {qualified} LIMIT {SAMPLE_ROWS}",
                    max_rows=SAMPLE_ROWS,
                    timeout_seconds=60,
                )
            except QueryFailed as exc:
                log.warning("introspect_table_failed", table=info.name, error=str(exc)[:200])
                continue
            frame = pd.DataFrame(sample.rows, columns=[c["name"] for c in sample.columns])
            for column in frame.columns:
                if frame[column].dtype == object:
                    converted = pd.to_datetime(frame[column], errors="coerce", format="ISO8601")
                    non_null = frame[column].notna().sum()
                    if non_null and converted.notna().sum() == non_null:
                        frame[column] = converted
            local = f"t_{len(loaded)}"
            con.register("__frame", frame)
            con.execute(f"CREATE TABLE {quote_ident(local)} AS SELECT * FROM __frame")
            con.unregister("__frame")
            profile = profile_table(con, local)
            profile.name = info.name
            true_rows = int(count.rows[0][0]) if count.rows else profile.row_count
            sampled = true_rows > len(frame)
            profile.row_count = true_rows
            profile.table["row_count"] = true_rows
            profile.table["sampled"] = sampled
            profile.table["sample_rows"] = len(frame)
            if sampled:
                profile.table["warnings"].append(
                    f"Profile computed on a sample of {len(frame):,} of {true_rows:,} rows"
                )
            profiles.append(profile)
            loaded.append(
                LoadedTable(
                    name=info.name,
                    display_name=info.name,
                    original_columns=list(frame.columns),
                    columns=list(frame.columns),
                    row_count=true_rows,
                )
            )
    finally:
        con.close()
    return persist_tables(db, source, loaded, profiles, None)
