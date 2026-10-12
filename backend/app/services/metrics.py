"""Saved business metric definitions ("average order value = SUM(revenue) / COUNT(*)").

A definition is a single SQL aggregate expression over one table's columns. It is validated with the same AST
validator as every other query (as `SELECT <expression> FROM <table>`), must aggregate (otherwise it is a column,
not a metric), and may not contain subqueries. The agent receives the definitions in its context and computes them
through the compute_metric tool, so "AOV" always means the team's definition rather than the model's guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.core.errors import ValidationFailed
from app.services.sql.validator import Catalog, validate_sql

NAME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


@dataclass
class ValidatedMetric:
    expression: str  # normalised SQL in the source dialect
    columns: list[str]


def validate_metric(
    expression: str, table: str, columns: dict[str, str], dialect: str, catalog: Catalog
) -> ValidatedMetric:
    text = (expression or "").strip().rstrip(";")
    if not text or len(text) > 2000:
        raise ValidationFailed("The metric expression is empty or too long")
    try:
        node = sqlglot.parse_one(text, read=dialect)
    except Exception as exc:
        raise ValidationFailed(f"The metric expression is not valid SQL: {str(exc)[:160]}") from exc
    if isinstance(node, exp.Query) or node.find(exp.Select, exp.Subquery):
        raise ValidationFailed("A metric is one expression such as SUM(revenue) / COUNT(*), not a query")
    if node.find(exp.AggFunc) is None:
        raise ValidationFailed("A metric must aggregate, for example SUM(...), AVG(...) or COUNT(...)")
    known = {c.lower() for c in columns}
    used = sorted({c.name for c in node.find_all(exp.Column)})
    unknown = [c for c in used if c.lower() not in known]
    if unknown:
        raise ValidationFailed(f"Unknown column(s) in metric: {', '.join(unknown)}")
    probe = exp.select(node.copy().as_("metric_value")).from_(exp.to_table(table, quoted=True)).sql(dialect=dialect)
    result = validate_sql(probe, dialect, catalog)
    if not result.ok:
        raise ValidationFailed(f"Metric rejected by the SQL validator: {result.error_message()}")
    return ValidatedMetric(expression=node.sql(dialect=dialect), columns=used)


def validate_name(name: str) -> str:
    value = (name or "").strip().lower()
    if not NAME.match(value):
        raise ValidationFailed("Metric names use lowercase letters, digits and underscores, e.g. avg_order_value")
    return value
