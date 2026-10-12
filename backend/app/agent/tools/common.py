"""Helpers shared by the analysis tools."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.agent.context import ToolContext, fmt_number, fmt_pct, sanitize_value
from app.agent.tools.base import FindingDraft, ToolError
from app.core.errors import ValidationFailed
from app.db.models import TableMetadata
from app.services.analytics.querybuilder import Filter, MetricSpec, Period, QueryBuilder, parse_period
from app.services.analytics.stats import pct_change
from app.services.datasources.base import QueryResult
from app.services.sql.executor import run_sql

INTERNAL_MAX_ROWS = 500_000


class TableArgs(BaseModel):
    table: str | None = Field(None, description="Table name; optional when the source has one table")
    filters: list[Filter] = Field(default_factory=list, description="Row filters applied before aggregation")


def builder(ctx: ToolContext, table: TableMetadata) -> QueryBuilder:
    return QueryBuilder(table.name, ctx.columns(table), ctx.engine.dialect)


def query(
    ctx: ToolContext, sql: str, *, max_rows: int | None = None, internal: bool = False
) -> tuple[QueryResult, str]:
    """Run SQL through the validator + audit log. Returns the result and the SQLExecution id."""
    run = run_sql(
        ctx.db,
        ctx.engine,
        ctx.catalog,
        sql,
        analysis_id=ctx.analysis_id,
        tool_execution_id=ctx.current_execution_id,
        max_rows=INTERNAL_MAX_ROWS if internal else max_rows,
        row_cap=INTERNAL_MAX_ROWS if internal else None,
    )
    if not run.ok or run.result is None:
        raise ToolError(
            run.error_kind or "execution_error",
            f"SQL {run.status}: {run.error}",
            {k: v for k, v in run.error_context().items() if k in {"suggestions", "available", "column", "table"}},
        )
    if internal and run.result.truncated:
        raise ToolError(
            "too_large", f"The query returned more than {INTERNAL_MAX_ROWS:,} rows; add filters or aggregate further"
        )
    return run.result, run.record_id or ""


def frame(result: QueryResult) -> pd.DataFrame:
    return pd.DataFrame(result.rows, columns=[c["name"] for c in result.columns])


def resolve_period(ctx: ToolContext, table: TableMetadata, spec: Any, date_column: str | None) -> Period:
    reference = None
    if date_column:
        column = next((c for c in table.columns if c.name.lower() == date_column.lower()), None)
        if column and column.stats.get("max"):
            reference = dt.date.fromisoformat(str(column.stats["max"])[:10])
    try:
        return parse_period(spec, reference)
    except ValidationFailed as exc:
        raise ToolError("bad_period", exc.message) from exc


def require_date_column(ctx: ToolContext, table: TableMetadata, date_column: str | None) -> str:
    column = date_column or ctx.default_date_column(table)
    if not column:
        raise ToolError(
            "invalid_arguments",
            f"Table '{table.name}' has no date column; pass date_column",
            {"available": [c.name for c in table.columns]},
        )
    match = next((c for c in table.columns if c.name.lower() == column.lower()), None)
    if match is None:
        from app.services.sql.validator import suggest

        dates = [c.name for c in table.columns if c.inferred_type in {"date", "datetime"}]
        options = suggest(column, [c.name for c in table.columns]) or dates[:1]
        raise ToolError(
            "unknown_column",
            f"Unknown date column '{column}'." + (f" Did you mean: {', '.join(options)}?" if options else ""),
            {"column": column, "suggestions": options, "available": dates},
        )
    if match.inferred_type not in {"date", "datetime"}:
        raise ToolError(
            "type_error",
            f"Column '{match.name}' is not a date column",
            {"available": [c.name for c in table.columns if c.inferred_type in {"date", "datetime"}]},
        )
    return match.name


def metric_label(metric: MetricSpec) -> str:
    if metric.agg == "count" and not metric.column:
        return "number of rows"
    names = {
        "sum": "total",
        "avg": "average",
        "count": "count of",
        "count_distinct": "distinct count of",
        "min": "minimum",
        "max": "maximum",
        "median": "median",
    }
    return f"{names[metric.agg]} {metric.column}"


def filters_text(filters: list[Filter]) -> str:
    if not filters:
        return ""
    parts = []
    for f in filters:
        value = f.value if not isinstance(f.value, list) else ", ".join(map(str, f.value))
        parts.append(f"{f.column} {f.op} {sanitize_value(value, 40)}")
    return " where " + " and ".join(parts)


def filter_entities(filters: list[Filter]) -> list[str]:
    entities: list[str] = []
    for f in filters:
        values = f.value if isinstance(f.value, list) else [f.value]
        entities.extend(str(v) for v in values if isinstance(v, str))
    return entities


def ranking_findings(
    data: pd.DataFrame,
    dim: str,
    value_col: str,
    label: str,
    *,
    context: str = "",
    periods: list[str] | None = None,
    limit: int = 12,
    extra_entities: list[str] | None = None,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    if data.empty:
        return findings
    total = float(pd.to_numeric(data[value_col], errors="coerce").sum())
    ordered = data.sort_values(value_col, ascending=False).reset_index(drop=True)
    for index, (_, row) in enumerate(ordered.head(limit).iterrows()):
        value = row[value_col]
        share = (float(value) / total * 100) if total and value is not None else None
        entity = str(row[dim])
        findings.append(
            FindingDraft(
                kind="ranking",
                statement=f"{label} for {dim} = {entity}{context}: {fmt_number(value)} "
                f"(rank {index + 1} of {len(ordered)}" + (f", {share:.2f}% of total)" if share is not None else ")"),
                values={"value": value, "rank": index + 1, "share_pct": share, "total": total},
                formula=f"share = {fmt_number(value)} / {fmt_number(total)} * 100" if share is not None else None,
                entities=[entity, *(extra_entities or [])],
                periods=periods or [],
                payload={"dimension": dim, "segment": entity},
            )
        )
    if len(ordered) > 1:
        top, bottom = ordered.iloc[0], ordered.iloc[-1]
        findings.append(
            FindingDraft(
                kind="ranking",
                statement=f"Highest {label}{context}: {dim} = {top[dim]} ({fmt_number(top[value_col])}); lowest: "
                f"{bottom[dim]} ({fmt_number(bottom[value_col])}); total across {len(ordered)} "
                f"{dim} values: {fmt_number(total)}",
                values={
                    "top_value": top[value_col],
                    "bottom_value": bottom[value_col],
                    "total": total,
                    "group_count": len(ordered),
                },
                entities=[str(top[dim]), str(bottom[dim]), *(extra_entities or [])],
                periods=periods or [],
                payload={"dimension": dim, "top": str(top[dim]), "bottom": str(bottom[dim])},
            )
        )
    return findings


def series_findings(
    data: pd.DataFrame,
    period_col: str,
    value_col: str,
    label: str,
    *,
    context: str = "",
    limit: int = 36,
    entities: list[str] | None = None,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    data = data.sort_values(period_col).reset_index(drop=True)
    tail = data.tail(limit).reset_index(drop=True)
    previous = None
    for _, row in tail.iterrows():
        period = str(row[period_col])[:10]
        value = row[value_col]
        findings.append(
            FindingDraft(
                kind="value",
                statement=f"{label}{context} in period starting {period}: {fmt_number(value)}",
                values={"value": value},
                periods=[period],
                entities=entities or [],
                payload={"period": period},
            )
        )
        if previous is not None and value is not None and previous[1] is not None:
            change = pct_change(float(previous[1]), float(value))
            findings.append(
                FindingDraft(
                    kind="comparison",
                    statement=f"{label}{context} changed from {fmt_number(previous[1])} ({previous[0]}) to "
                    f"{fmt_number(value)} ({period}): {fmt_pct(change)}",
                    values={
                        "previous": previous[1],
                        "current": value,
                        "change": float(value) - float(previous[1]),
                        "pct_change": change,
                    },
                    formula=f"({fmt_number(value)} - {fmt_number(previous[1])}) / {fmt_number(previous[1])} * 100",
                    periods=[previous[0], period],
                    entities=entities or [],
                    payload={"previous_period": previous[0], "current_period": period},
                )
            )
        previous = (period, value)
    return findings


def rows_findings(result_name: str, columns: list[str], rows: list[list[Any]], limit: int = 25) -> list[FindingDraft]:
    """Generic findings for arbitrary query/code results: one per row (bounded)."""
    findings: list[FindingDraft] = []
    for row in rows[:limit]:
        values = {
            c: v for c, v in zip(columns, row, strict=False) if isinstance(v, int | float) and not isinstance(v, bool)
        }
        entities = [str(v) for v in row if isinstance(v, str)]
        rendered = ", ".join(
            f"{c}={fmt_number(v) if isinstance(v, int | float) and not isinstance(v, bool) else sanitize_value(v, 40)}"
            for c, v in zip(columns, row, strict=False)
        )
        findings.append(
            FindingDraft(
                kind="value",
                statement=f"{result_name} row: {rendered}",
                values=values,
                entities=entities,
                periods=[e[:10] for e in entities if _looks_like_date(e)],
            )
        )
    return findings


def _looks_like_date(text: str) -> bool:
    try:
        dt.date.fromisoformat(text[:10])
        return True
    except ValueError:
        return False


def compact_table(columns: list[str], rows: list[list[Any]], limit: int = 15) -> str:
    """Render a small preview for the LLM observation (sanitized, bounded)."""
    lines = [" | ".join(columns)]
    for row in rows[:limit]:
        lines.append(
            " | ".join(
                fmt_number(v) if isinstance(v, int | float) and not isinstance(v, bool) else str(sanitize_value(v, 30))
                for v in row
            )
        )
    if len(rows) > limit:
        lines.append(f"... ({len(rows) - limit} more rows)")
    return "\n".join(lines)


_FREQ = {"day": "D", "week": "W-MON", "month": "MS", "quarter": "QS", "year": "YS"}


def complete_series(
    series: pd.Series, grain: str, agg: str, start: dt.date | None = None, end: dt.date | None = None
) -> pd.Series:
    """Fill periods with no rows. A day without orders is a real zero for sum/count, unknown for averages.

    GROUP BY never returns empty buckets, so without this an outage day would silently vanish from the series.
    """
    if series.empty:
        return series
    index = pd.to_datetime(pd.Series(series.index.astype(str)).str[:10])
    data = pd.Series(series.to_numpy(), index=pd.DatetimeIndex(index))
    first = pd.Timestamp(start) if start else data.index.min()
    last = pd.Timestamp(end) if end else data.index.max()
    if grain != "day":
        first = data.index.min() if start is None else first.to_period(_FREQ[grain][0]).start_time
    full = pd.date_range(first, last, freq=_FREQ.get(grain, "D"))
    if grain == "week":
        full = pd.date_range(first - pd.Timedelta(days=first.weekday()), last, freq="W-MON")
    fill = 0.0 if agg in {"sum", "count", "count_distinct"} else None
    completed = data.groupby(level=0).sum(min_count=1).reindex(full.union(pd.DatetimeIndex(data.index)))
    if fill is not None:
        completed = completed.fillna(fill)
    completed.index = pd.Index(pd.DatetimeIndex(completed.index).strftime("%Y-%m-%d"))
    return completed


def clip_to_data(
    table: TableMetadata, date_column: str | None, start: dt.date | None, end: dt.date | None
) -> tuple[dt.date | None, dt.date | None]:
    """Never extend a series beyond the data's real date range (no fake zeros for months not yet recorded)."""
    column = next((c for c in table.columns if date_column and c.name.lower() == date_column.lower()), None)
    stats = (column.stats or {}) if column else {}
    lo = dt.date.fromisoformat(str(stats["min"])[:10]) if stats.get("min") else None
    hi = dt.date.fromisoformat(str(stats["max"])[:10]) if stats.get("max") else None
    if start and lo:
        start = max(start, lo)
    if end and hi:
        end = min(end, hi)
    return start, end
