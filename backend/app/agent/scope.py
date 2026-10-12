"""Plan scope check: does the plan answer the question that was asked?

Number verification proves that every number came from a computation; it cannot prove the computation was the
right one. The most common way a small model goes wrong is by narrowing the question: adding a filter or a time
window nobody asked for ("customers who expanded" silently becomes "customers who expanded and did not churn").

This module finds such restrictions deterministically before any tool runs:
  * filters (tool `filters` arguments and WHERE/HAVING conditions in model-written SQL) whose column and value
    are not mentioned in the question or the active conversation context,
  * period restrictions when the question contains no time reference at all,
and the opposite mistake: an explicit period in the question ("in 2026", "Q2", "March") that no step applies.
The orchestrator asks the planner to fix them once; anything left is reported to the user as an assumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from app.agent.schemas import Plan, PlanStep

GENERIC_TOKENS = {
    "date",
    "time",
    "id",
    "ids",
    "total",
    "value",
    "values",
    "count",
    "amount",
    "name",
    "type",
    "code",
    "num",
    "pct",
    "usd",
    "col",
    "the",
    "and",
    "per",
    "flag",
    "is",
    "has",
}
TIME_WORDS = re.compile(
    r"\b(19|20)\d{2}\b|\bq[1-4]\b|\bh[12]\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
    r"\b(quarters?|quarterly|months?|monthly|years?|yearly|annual|weeks?|weekly|days?|daily|today|yesterday|last|latest|"
    r"summer|winter|spring|autumn|fall|holidays?|weekends?|weekdays?|tonight|tomorrow|"
    r"recent|recently|previous|prior|ytd|mtd|since|before|after|between|during|until|trend|trends|over time|"
    r"growth|season|seasonal|period|periods|timeline|history|historical)\b",
    re.IGNORECASE,
)
PERIOD_KEYS = ("period", "current_period", "previous_period")
# Explicit periods only ("may" is left out: it is far more often a verb).
_YEAR = re.compile(r"(?<![\d.,$])((?:19|20)\d{2})(?![\d%])")
EXPLICIT_PERIOD = re.compile(
    r"(?<![\d.,$])(?:19|20)\d{2}(?![\d%])|\bq[1-4]\b|\bh[12]\b|"
    r"\b(?:january|february|march|april|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
_DATE_LITERAL = re.compile(r"'\d{4}-\d{2}(?:-\d{2})?'|\b(?:year|quarter|month|date_trunc|strftime|extract)\s*\(", re.I)
_TIME_COLUMN = re.compile(r"date|time|month|year|quarter|week|day|period|_at$|_on$", re.IGNORECASE)
NON_COMPUTING_TOOLS = {
    "list_tables",
    "describe_table",
    "inspect_schema",
    "profile_dataset",
    "create_chart",
    "retrieve_evidence",
    "retrieve_previous_analysis",
    "generate_report",
}


@dataclass
class ScopeIssue:
    step_id: str
    kind: str  # filter | period | missing_period
    detail: str
    column: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ScopeContext:
    question: str
    allowed_text: str = ""  # earlier questions + active filters (follow-ups may refer to them)
    active_columns: set[str] = field(default_factory=set)
    data_years: set[str] | None = None  # years the data spans: "in 2026" needs no filter when all data is 2026

    @property
    def text(self) -> str:
        return f"{self.question}\n{self.allowed_text}".lower()


def _significant_tokens(column: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", column.lower()) if len(t) >= 4 and t not in GENERIC_TOKENS]


def column_mentioned(column: str, text: str) -> bool:
    lowered = column.lower()
    if lowered in text or lowered.replace("_", " ") in text:
        return True
    words = re.findall(r"[a-z0-9]+", text)
    for token in _significant_tokens(column):
        stem = token[:5]
        if any(word.startswith(stem) for word in words):
            return True
    return False


def value_mentioned(value: Any, text: str) -> bool:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if item is None or isinstance(item, bool):
            continue
        rendered = str(item).strip().lower()
        if rendered and rendered in text:
            return True
    return False


def _filter_issue(step: PlanStep, column: str, value: Any, ctx: ScopeContext, how: str) -> ScopeIssue | None:
    text = ctx.text
    if column.lower() in ctx.active_columns or column_mentioned(column, text) or value_mentioned(value, text):
        return None
    shown = f"{column} {how}".strip()
    return ScopeIssue(
        step.id, "filter", f"'{step.title}' restricts {shown}, which the question does not mention", column
    )


def _sql_condition_columns(sql: str, dialect: str) -> list[tuple[str, str]]:
    """Columns that WHERE/HAVING conditions pin to fixed values (equality, IN, IS NULL, ranges, LIKE).

    Conditions comparing two columns (mrr > initial_mrr) define the quantity being asked about rather than
    narrowing the population, so they are not treated as restrictions. Join conditions are ignored.
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return []
    found: list[tuple[str, str]] = []
    for clause in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Having)):
        for predicate in _predicates(clause.this):
            columns = list(predicate.find_all(exp.Column))
            if len({c.name.lower() for c in columns}) != 1:
                continue
            found.append((columns[0].name, predicate.sql(dialect=dialect)[:120]))
    return found


def _predicates(node: exp.Expr) -> list[exp.Expr]:
    if isinstance(node, exp.And | exp.Or):
        return _predicates(node.left) + _predicates(node.right)
    if isinstance(node, exp.Paren):
        return _predicates(node.this)
    return [node]


def check_plan_scope(plan: Plan, ctx: ScopeContext, dialect: str) -> list[ScopeIssue]:
    issues: list[ScopeIssue] = []
    has_time_reference = bool(TIME_WORDS.search(ctx.text))
    for step in plan.steps:
        args = step.args or {}
        for flt in args.get("filters") or []:
            if isinstance(flt, dict) and flt.get("column"):
                op = str(flt.get("op", "="))
                issue = _filter_issue(step, str(flt["column"]), flt.get("value"), ctx, f"({op} {flt.get('value')})")
                if issue:
                    issues.append(issue)
        if step.tool == "execute_sql" and isinstance(args.get("sql"), str):
            seen: set[str] = set()
            for column, condition in _sql_condition_columns(args["sql"], dialect):
                key = column.lower()
                if key in seen:
                    continue
                seen.add(key)
                issue = _filter_issue(step, column, None, ctx, f"(SQL condition: {condition})")
                if issue:
                    issues.append(issue)
        if not has_time_reference and any(args.get(key) for key in PERIOD_KEYS):
            labels = ", ".join(str(args.get(k)) for k in PERIOD_KEYS if args.get(k))
            issues.append(
                ScopeIssue(
                    step.id,
                    "period",
                    f"'{step.title}' limits the analysis to {labels}, but the question does not mention a time period",
                )
            )
    gap = missing_period(plan, ctx)
    if gap:
        issues.append(gap)
    return issues


def _restricts_time(step: PlanStep) -> bool:
    args = step.args or {}
    if any(args.get(key) for key in (*PERIOD_KEYS, "time_grain", "start", "end", "start_date", "end_date")):
        return True
    for flt in args.get("filters") or []:
        if isinstance(flt, dict) and _TIME_COLUMN.search(str(flt.get("column", ""))):
            return True
    code = " ".join(str(args.get(key) or "") for key in ("sql", "code"))
    return bool(code and (_DATE_LITERAL.search(code) or _YEAR.search(code)))


def missing_period(plan: Plan, ctx: ScopeContext) -> ScopeIssue | None:
    """The question names a period ("in 2026", "Q2", "March") but no step restricts or groups by time."""
    named = [m.group(0) for m in EXPLICIT_PERIOD.finditer(ctx.question)]
    if not named:
        return None
    years = {n for n in named if _YEAR.fullmatch(n)}
    if len(years) == len(named) and ctx.data_years and ctx.data_years <= years:
        return None  # all of the data lies in the named year(s)
    computing = [s for s in plan.steps if s.tool not in NON_COMPUTING_TOOLS]
    if not computing or any(_restricts_time(s) for s in plan.steps):
        return None
    step = computing[0]
    shown = ", ".join(dict.fromkeys(named))
    return ScopeIssue(
        step.id, "missing_period", f"the question asks about {shown}, but no step restricts the data to that period"
    )


def describe(issues: list[ScopeIssue]) -> str:
    return "\n".join(f"- step {i.step_id}: {i.detail}" for i in issues)
