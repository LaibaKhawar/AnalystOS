"""Builds aggregation SQL for the deterministic analysis tools.

Tools never interpolate LLM-provided strings into SQL text: identifiers are checked against the catalog
and quoted, values become escaped literals via sqlglot. The generated SQL still goes through the same
validator and audit log as LLM-written SQL, so every number has a stored, re-runnable query behind it.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
import sqlglot
from sqlglot import exp

from app.core.errors import ValidationFailed

FilterOp = Literal["=", "!=", ">", ">=", "<", "<=", "in", "not_in", "between", "contains", "is_null", "not_null"]
Aggregation = Literal["sum", "avg", "count", "count_distinct", "min", "max", "median"]


class Filter(BaseModel):
    column: str
    op: FilterOp = "="
    value: Any = None

    @field_validator("op", mode="before")
    @classmethod
    def _normalise_op(cls, value: Any) -> Any:
        aliases = {"==": "=", "eq": "=", "<>": "!=", "ne": "!=", "not in": "not_in", "gte": ">=", "lte": "<=",
                   "gt": ">", "lt": "<", "like": "contains", "is null": "is_null", "is not null": "not_null"}
        return aliases.get(str(value).lower(), value) if isinstance(value, str) else value


class MetricSpec(BaseModel):
    column: str | None = Field(None, description="Numeric column; omit for row counts")
    agg: Aggregation = "sum"

    def label(self) -> str:
        """Result column name: sum(revenue) -> 'revenue', avg(revenue) -> 'avg_revenue', count(*) -> 'row_count'."""
        if self.agg == "count" and not self.column:
            return "row_count"
        if self.agg == "sum" and self.column:
            return self.column
        return f"{self.agg}_{self.column}" if self.column else self.agg


@dataclass
class Period:
    label: str
    start: dt.date
    end: dt.date  # inclusive

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "start": self.start.isoformat(), "end": self.end.isoformat()}


def _quarter_bounds(year: int, quarter: int) -> tuple[dt.date, dt.date]:
    start_month = 3 * (quarter - 1) + 1
    end_month = start_month + 2
    return dt.date(year, start_month, 1), dt.date(year, end_month, calendar.monthrange(year, end_month)[1])


def parse_period(spec: str | dict[str, Any], reference_max: dt.date | None = None) -> Period:
    """Accepts '2026-Q3', 'Q3 2026', '2026-07', 'July 2026', '2026', 'H1 2026', '2026-01-01..2026-03-31',
    {'start': ..., 'end': ...}, and relative labels resolved against the data's latest date:
    'latest_month', 'previous_month', 'latest_quarter', 'previous_quarter', 'latest_year', 'previous_year'."""
    if isinstance(spec, dict):
        try:
            start = dt.date.fromisoformat(str(spec["start"])[:10])
            end = dt.date.fromisoformat(str(spec["end"])[:10])
        except (KeyError, ValueError) as exc:
            raise ValidationFailed("Period objects need ISO 'start' and 'end' dates") from exc
        return Period(spec.get("label") or f"{start}..{end}", start, end)
    text = str(spec).strip()
    lowered = text.lower().replace(" ", "")

    if lowered.startswith(("latest_", "previous_", "last_")):
        if reference_max is None:
            raise ValidationFailed("Relative periods need a date column in the data")
        unit = lowered.split("_", 1)[1]
        offset = 1 if lowered.startswith("previous_") else 0
        ref = reference_max
        if unit == "month":
            month_index = ref.year * 12 + ref.month - 1 - offset
            year, month = divmod(month_index, 12)
            return parse_period(f"{year}-{month + 1:02d}")
        if unit == "quarter":
            q_index = ref.year * 4 + (ref.month - 1) // 3 - offset
            year, q = divmod(q_index, 4)
            return parse_period(f"{year}-Q{q + 1}")
        if unit == "year":
            return parse_period(str(ref.year - offset))
        raise ValidationFailed(f"Unsupported relative period '{text}'")

    if ".." in text:
        a, b = (part.strip() for part in text.split("..", 1))
        try:
            return Period(text, dt.date.fromisoformat(a[:10]), dt.date.fromisoformat(b[:10]))
        except ValueError:
            first, last = parse_period(a, reference_max), parse_period(b, reference_max)
            return Period(f"{first.label}..{last.label}", first.start, last.end)
    m = re.fullmatch(r"(\d{4})-?q([1-4])", lowered) or re.fullmatch(r"q([1-4])-?(\d{4})", lowered)
    if m:
        year, q = (int(m.group(1)), int(m.group(2))) if len(m.group(1)) == 4 else (int(m.group(2)), int(m.group(1)))
        start, end = _quarter_bounds(year, q)
        return Period(f"{year}-Q{q}", start, end)
    m = re.fullmatch(r"(\d{4})-?h([12])", lowered) or re.fullmatch(r"h([12])-?(\d{4})", lowered)
    if m:
        year, half = (int(m.group(1)), int(m.group(2))) if len(m.group(1)) == 4 else (int(m.group(2)), int(m.group(1)))
        return Period(f"{year}-H{half}", dt.date(year, 1 if half == 1 else 7, 1),
                      dt.date(year, 6, 30) if half == 1 else dt.date(year, 12, 31))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", lowered)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        return Period(f"{year}-{month:02d}", dt.date(year, month, 1),
                      dt.date(year, month, calendar.monthrange(year, month)[1]))
    for fmt in ("%B%Y", "%b%Y", "%Y%B", "%Y%b"):
        try:
            parsed = dt.datetime.strptime(lowered, fmt)
            return parse_period(f"{parsed.year}-{parsed.month:02d}")
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}", lowered):
        year = int(lowered)
        return Period(str(year), dt.date(year, 1, 1), dt.date(year, 12, 31))
    try:
        day = dt.date.fromisoformat(text[:10])
        return Period(text[:10], day, day)
    except ValueError as exc:
        raise ValidationFailed(
            f"Could not understand period '{text}'. Use forms like 2026-Q3, 2026-07, 2026, or 2026-01-01..2026-03-31"
        ) from exc


class QueryBuilder:
    """Generates catalog-checked SQL for one table."""

    def __init__(self, table: str, columns: dict[str, str], dialect: str) -> None:
        self.table = table
        self.columns = {c.lower(): c for c in columns}
        self.types = {c.lower(): t for c, t in columns.items()}
        self.dialect = dialect

    def col(self, name: str) -> exp.Column:
        key = (name or "").lower().strip()
        if key not in self.columns:
            from app.services.sql.validator import suggest

            options = suggest(key, list(self.columns))
            hint = f" Did you mean: {', '.join(options)}?" if options else ""
            raise ValidationFailed(f"Unknown column '{name}' in table '{self.table}'.{hint}",
                                   details={"kind": "unknown_column", "column": name, "suggestions": options,
                                            "available": sorted(self.columns.values())})
        return exp.column(self.columns[key], quoted=True)

    def is_numeric(self, name: str) -> bool:
        t = self.types.get(name.lower(), "").upper()
        return any(k in t for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL"))

    def metric_expr(self, metric: MetricSpec) -> exp.Expression:
        if metric.agg == "count":
            return exp.Count(this=self.col(metric.column) if metric.column else exp.Star())
        if not metric.column:
            raise ValidationFailed(f"Aggregation '{metric.agg}' needs a column")
        column = self.col(metric.column)
        if metric.agg == "count_distinct":
            return exp.Count(this=exp.Distinct(expressions=[column]))
        if not self.is_numeric(metric.column):
            raise ValidationFailed(f"Column '{metric.column}' is not numeric; use agg='count' or 'count_distinct'",
                                   details={"kind": "type_error", "column": metric.column})
        if metric.agg == "median":
            if self.dialect == "duckdb":
                return exp.Anonymous(this="median", expressions=[column])
            if self.dialect == "postgres":
                return sqlglot.parse_one(
                    f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {column.sql(dialect='postgres')})", read="postgres"
                )
            raise ValidationFailed("median is not available on this database; use agg='avg'")
        func = {"sum": exp.Sum, "avg": exp.Avg, "min": exp.Min, "max": exp.Max}[metric.agg]
        return func(this=column)

    def literal(self, value: Any) -> exp.Expression:
        if value is None:
            return exp.Null()
        if isinstance(value, bool):
            return exp.Boolean(this=value)
        if isinstance(value, int | float):
            return exp.Literal.number(value)
        return exp.Literal.string(str(value))

    def condition(self, flt: Filter) -> exp.Expression:
        column = self.col(flt.column)
        op, value = flt.op, flt.value
        if op == "is_null":
            return exp.Is(this=column, expression=exp.Null())
        if op == "not_null":
            return exp.Not(this=exp.Is(this=column, expression=exp.Null()))
        if op in {"in", "not_in"}:
            values = value if isinstance(value, list) else [value]
            node: exp.Expression = exp.In(this=column, expressions=[self.literal(v) for v in values])
            return exp.Not(this=node) if op == "not_in" else node
        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ValidationFailed("'between' needs a two-element list")
            return exp.Between(this=column, low=self.literal(value[0]), high=self.literal(value[1]))
        if op == "contains":
            return exp.ILike(this=exp.cast(column, "TEXT"), expression=exp.Literal.string(f"%{value}%"))
        cls = {"=": exp.EQ, "!=": exp.NEQ, ">": exp.GT, ">=": exp.GTE, "<": exp.LT, "<=": exp.LTE}[op]
        return cls(this=column, expression=self.literal(value))

    def period_condition(self, date_column: str, period: Period) -> exp.Expression:
        column = self.col(date_column)
        return exp.and_(
            exp.GTE(this=column, expression=exp.cast(exp.Literal.string(period.start.isoformat()), "DATE")),
            exp.LT(this=column, expression=exp.cast(
                exp.Literal.string((period.end + dt.timedelta(days=1)).isoformat()), "DATE")),
        )

    def where(self, filters: list[Filter], extra: list[exp.Expression] | None = None) -> exp.Expression | None:
        conditions = [self.condition(f) for f in filters] + list(extra or [])
        if not conditions:
            return None
        return exp.and_(*conditions)

    def time_bucket(self, date_column: str, grain: str) -> exp.Expression:
        grain = grain.lower()
        if grain not in {"day", "week", "month", "quarter", "year"}:
            raise ValidationFailed("grain must be one of day, week, month, quarter, year")
        column = self.col(date_column)
        if self.dialect == "mysql":
            fmt = {"day": "%Y-%m-%d", "week": "%x-W%v", "month": "%Y-%m-01", "quarter": None, "year": "%Y-01-01"}[grain]
            if grain == "quarter":
                return exp.Anonymous(this="MAKEDATE", expressions=[exp.Anonymous(this="YEAR", expressions=[column]),
                                                                   exp.Literal.number(1)])
            return exp.Anonymous(this="DATE_FORMAT", expressions=[column, exp.Literal.string(fmt)])
        if self.dialect == "sqlite":
            fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m-01", "quarter": "%Y-%m-01",
                   "year": "%Y-01-01"}[grain]
            return exp.Anonymous(this="strftime", expressions=[exp.Literal.string(fmt), column])
        return exp.cast(exp.DateTrunc(this=column, unit=exp.Literal.string(grain)), "DATE")

    def select(
        self, projections: list[exp.Expression], *, filters: list[Filter] | None = None,
        extra_conditions: list[exp.Expression] | None = None, group_by: list[exp.Expression] | None = None,
        order_by: list[exp.Expression] | None = None, limit: int | None = None,
    ) -> str:
        query = exp.select(*projections).from_(exp.to_table(self.table, quoted=True))
        condition = self.where(filters or [], extra_conditions)
        if condition is not None:
            query = query.where(condition)
        if group_by:
            query = query.group_by(*group_by)
        if order_by:
            query = query.order_by(*order_by)
        if limit:
            query = query.limit(limit)
        return query.sql(dialect=self.dialect)
