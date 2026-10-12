"""Fast path for simple whole-table statistics ("What is the average revenue?").

These questions are fully answered by the precomputed dataset profile, so the planner and synthesizer LLM calls add
latency without adding value. A deliberately strict matcher recognises them; anything with a dimension, filter value,
time reference, ranking or comparison goes to the normal agent. The answer is built from a profile finding and still
passes through the same verifier as every other answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent.context import fmt_number
from app.agent.schemas import Draft, DraftItem, Plan, PlanStep
from app.agent.scope import TIME_WORDS, column_mentioned
from app.db.models import DataSource, Finding, TableMetadata

AGGREGATES: list[tuple[str, str, str]] = [
    # (regex, stat key in the column profile, phrase)
    (r"\b(average|mean|avg)\b", "mean", "average"),
    (r"\bmedian\b", "median", "median"),
    (r"\b(total|sum)\b", "sum", "total"),
    (r"\b(standard deviation|std|stdev)\b", "std", "standard deviation"),
    (r"\b(minimum|min|smallest|lowest)\b", "min", "minimum"),
    (r"\b(maximum|max|largest|highest)\b", "max", "maximum"),
    (r"\b(missing|null|blank|empty)\b", "missing_pct", "share of missing values in"),
    (r"\b(distinct|unique)\b", "distinct", "number of distinct values in"),
]
ROW_COUNT = re.compile(r"\bhow many (rows|records|entries|lines|transactions|orders)\b|\b(row|record) count\b", re.I)
DISQUALIFIERS = re.compile(
    r"\b(which|who|where|why|how did|compare|compared|versus|vs|trend|rank|ranking|top|bottom|by|per|each|"
    r"for|when|between|across|group|segment|excluding|except|without|only|if|whose|than)\b",
    re.IGNORECASE,
)


@dataclass
class FastPathMatch:
    table: TableMetadata
    column: str | None  # None = table-level row count
    stat: str
    phrase: str

    def plan(self) -> Plan:
        columns = [self.column] if self.column else []
        return Plan(
            goal="Answer a whole-table statistic from the precomputed dataset profile",
            assumptions=["Answered from the dataset profile computed over all rows (no model call was needed)"],
            steps=[
                PlanStep(
                    id="s1",
                    title="Read the precomputed profile",
                    tool="profile_dataset",
                    args={"table": self.table.name, "columns": columns},
                )
            ],
        )


def match(question: str, source: DataSource) -> FastPathMatch | None:
    text = question.strip().lower()
    if len(text) > 160 or DISQUALIFIERS.search(text) or TIME_WORDS.search(text):
        return None
    tables = list(source.tables)
    if not tables:
        return None
    named = [t for t in tables if t.name.lower() in text or t.display_name.lower() in text]
    if len(tables) > 1 and len(named) != 1:
        return None
    table = named[0] if named else tables[0]
    if (table.profile or {}).get("sampled"):
        return None  # sample-based statistics are estimates; let the agent compute exactly
    for column in table.columns:  # a category value in the question means a filter, not a whole-table statistic
        if column.role == "dimension" and not column.is_pii:
            for top in (column.stats or {}).get("top_values", []):
                value = str(top.get("value", "")).lower()
                if len(value) >= 3 and re.search(rf"\b{re.escape(value)}\b", text):
                    return None
    mentioned = [c for c in table.columns if column_mentioned(c.name, text) and c.role != "identifier"]
    if ROW_COUNT.search(text) and not mentioned:
        return FastPathMatch(table, None, "rows", "number of rows in")
    for pattern, stat, phrase in AGGREGATES:
        if re.search(pattern, text):
            if len(mentioned) != 1:
                return None
            column = mentioned[0]
            numeric_only = stat in {"mean", "median", "sum", "std", "min", "max"}
            if numeric_only and column.inferred_type not in {"integer", "float"}:
                return None
            if column.is_pii and stat not in {"missing_pct", "distinct"}:
                return None
            return FastPathMatch(table, column.name, stat, phrase)
    return None


def draft_from_profile(found: FastPathMatch, findings: list[Finding]) -> Draft:
    """Deterministic answer text built from the profile finding (verified afterwards like any answer)."""
    if found.column is None:
        finding = next(f for f in findings if f.statement.startswith(f"Table {found.table.name}"))
        sentence = f"The {found.table.name} table has {fmt_number(finding.values.get('rows'))} rows."
    else:
        finding = next(f for f in findings if f.statement.startswith(f"Column {found.column} "))
        value = finding.values.get(found.stat)
        unit = "%" if found.stat == "missing_pct" else ""
        basis = ""
        if found.stat in {"mean", "median", "sum", "std", "min", "max"}:
            basis = f", computed over {fmt_number(finding.values.get('non_null'))} non-empty values"
        sentence = f"The {found.phrase} {found.column} is {fmt_number(value)}{unit}{basis}."
    item = DraftItem(text=sentence, citations=[finding.label])
    return Draft(
        headline=sentence,
        summary=[item],
        facts=[],
        caveats=[],
        follow_up_questions=[f"How does {found.column or 'this'} vary by segment or over time?"],
    )
