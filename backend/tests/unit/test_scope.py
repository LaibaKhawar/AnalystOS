from __future__ import annotations

import pytest

from app.agent.schemas import Plan
from app.agent.scope import ScopeContext, check_plan_scope, column_mentioned


def _plan(tool: str, args: dict) -> Plan:  # type: ignore[type-arg]
    return Plan(goal="g", steps=[{"id": "s1", "title": "Step", "tool": tool, "args": args}])


SQL_EXPANDED = "SELECT COUNT(*) FROM saas WHERE mrr > initial_mrr AND churn_date IS NULL"


def test_unrequested_sql_condition_is_flagged() -> None:
    question = "How many customers expanded, meaning their current mrr is above their initial_mrr?"
    issues = check_plan_scope(_plan("execute_sql", {"sql": SQL_EXPANDED}), ScopeContext(question), "duckdb")
    assert [i.column for i in issues] == ["churn_date"]


def test_requested_conditions_are_not_flagged() -> None:
    question = "How many active customers expanded? Exclude churned accounts."
    assert check_plan_scope(_plan("execute_sql", {"sql": SQL_EXPANDED}), ScopeContext(question), "duckdb") == []


@pytest.mark.parametrize(
    ("question", "flagged"),
    [
        ("Total revenue for Enterprise customers", False),  # value mentioned
        ("Revenue by customer segment", False),  # column mentioned
        ("Total revenue please", True),
    ],
)
def test_tool_filters(question: str, flagged: bool) -> None:
    args = {"metric": {"column": "revenue"}, "filters": [{"column": "customer_segment", "value": "Enterprise"}]}
    assert bool(check_plan_scope(_plan("aggregate_metric", args), ScopeContext(question), "duckdb")) is flagged


def test_follow_up_inherits_active_filters() -> None:
    args = {"metric": {"column": "revenue"}, "filters": [{"column": "region", "value": "Lahore"}]}
    ctx = ScopeContext("Show it monthly", allowed_text="Why did Lahore decline?", active_columns={"region"})
    assert check_plan_scope(_plan("aggregate_metric", args), ctx, "duckdb") == []


def test_period_without_time_reference() -> None:
    args = {"metric": {"column": "revenue"}, "group_by": ["region"], "period": "2026"}
    assert check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Which region sells most?"), "duckdb")
    assert not check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Top region in 2026?"), "duckdb")
    assert not check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Top region last year?"), "duckdb")


def test_column_comparisons_define_the_question_and_are_not_flagged() -> None:
    sql = "SELECT COUNT(*) FROM saas WHERE mrr > initial_mrr"
    assert check_plan_scope(_plan("execute_sql", {"sql": sql}), ScopeContext("How many accounts grew?"), "duckdb") == []


def test_seasons_count_as_time_references() -> None:
    args = {"metric": {"column": "revenue"}, "period": "2026-06-01..2026-08-31"}
    assert not check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Unusual days this summer?"), "duckdb")


def test_column_mention_uses_stems() -> None:
    assert column_mentioned("churn_date", "which customers churned")
    assert not column_mentioned("churn_date", "what was revenue on that date")
