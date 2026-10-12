"""Validated SQL execution with full audit logging (every statement is stored, including blocked ones)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import QUERY_DURATION, SQL_BLOCKED
from app.core.tracing import span
from app.db.models import SQLExecution
from app.services.datasources.base import QueryEngine, QueryFailed, QueryResult, QueryTimeout
from app.services.sql.validator import Catalog, SQLLimits, ValidationResult, validate_sql

log = get_logger(__name__)


@dataclass
class SQLRun:
    status: str  # success | blocked | error | timeout
    validation: ValidationResult
    result: QueryResult | None
    error: str | None
    error_kind: str | None
    record_id: str | None

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def error_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {"status": self.status, "error": self.error, "kind": self.error_kind}
        for err in self.validation.errors:
            for key in ("suggestions", "available", "column", "table"):
                if key in err:
                    context[key] = err[key]
        return context


def _run_sql(
    db: Session | None,
    engine: QueryEngine,
    catalog: Catalog,
    sql: str,
    *,
    analysis_id: str | None = None,
    tool_execution_id: str | None = None,
    max_rows: int | None = None,
    row_cap: int | None = None,
) -> SQLRun:
    settings = get_settings()
    limits = SQLLimits(
        # row_cap lets deterministic tools (which aggregate full columns) exceed the interactive cap.
        max_rows=min(max_rows or settings.sql_max_rows, row_cap or settings.sql_max_rows),
        max_joins=settings.sql_max_joins,
        max_subquery_depth=settings.sql_max_subquery_depth,
    )
    validation = validate_sql(sql, engine.dialect, catalog, limits)
    record = SQLExecution(
        analysis_id=analysis_id,
        tool_execution_id=tool_execution_id,
        dialect=engine.dialect,
        sql_original=sql,
        sql_executed=validation.safe_sql,
        validation=validation.to_dict(),
        status="blocked",
    )
    run: SQLRun
    if not validation.ok:
        kind = validation.errors[0]["kind"] if validation.errors else "invalid"
        SQL_BLOCKED.labels(reason=kind).inc()
        record.error = validation.error_message()
        log.info("sql_blocked", reason=kind, error=record.error)
        run = SQLRun("blocked", validation, None, record.error, kind, None)
    else:
        assert validation.safe_sql is not None
        try:
            result = engine.execute(
                validation.safe_sql, max_rows=limits.max_rows, timeout_seconds=settings.sql_timeout_seconds
            )
            record.status, record.row_count, record.truncated = "success", result.row_count, result.truncated
            record.duration_ms = result.duration_ms
            QUERY_DURATION.labels(dialect=engine.dialect, status="success").observe(result.duration_ms / 1000)
            run = SQLRun("success", validation, result, None, None, None)
        except QueryTimeout as exc:
            record.status, record.error = "timeout", str(exc)
            QUERY_DURATION.labels(dialect=engine.dialect, status="timeout").observe(settings.sql_timeout_seconds)
            run = SQLRun("timeout", validation, None, str(exc), "timeout", None)
        except QueryFailed as exc:
            record.status, record.error = "error", str(exc)
            QUERY_DURATION.labels(dialect=engine.dialect, status="error").observe(0)
            run = SQLRun("error", validation, None, str(exc), "execution_error", None)
    if db is not None:
        db.add(record)
        db.flush()
        run.record_id = record.id
    return run


def run_sql(
    db: Session | None,
    engine: QueryEngine,
    catalog: Catalog,
    sql: str,
    *,
    analysis_id: str | None = None,
    tool_execution_id: str | None = None,
    max_rows: int | None = None,
    row_cap: int | None = None,
) -> SQLRun:
    with span("sql.execute", **{"db.system": engine.dialect}) as current:
        run = _run_sql(
            db,
            engine,
            catalog,
            sql,
            analysis_id=analysis_id,
            tool_execution_id=tool_execution_id,
            max_rows=max_rows,
            row_cap=row_cap,
        )
        current.set_attribute("sql.status", run.status)
        if run.result is not None:
            current.set_attribute("sql.rows", run.result.row_count)
            current.set_attribute("sql.duration_ms", run.result.duration_ms)
        if run.error_kind:
            current.set_attribute("sql.error_kind", run.error_kind)
        return run
