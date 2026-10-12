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


AOV = {"name": "aov", "filters": [{"column": "customer_segment", "value": "Enterprise"}]}


def test_period_named_in_the_question_but_missing_from_the_plan() -> None:
    question = "What was the average revenue per order for Enterprise customers in 2026?"
    issues = check_plan_scope(
        _plan("compute_metric", AOV), ScopeContext(question, data_years={"2025", "2026"}), "duckdb"
    )
    assert [i.kind for i in issues] == ["missing_period"]
    assert "2026" in issues[0].detail


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("compute_metric", {**AOV, "period": "2026"}),
        ("aggregate_metric", {"metric": {"column": "revenue"}, "time_grain": "month"}),
        ("execute_sql", {"sql": "SELECT AVG(revenue) FROM sales WHERE year(date) = 2026"}),
        ("execute_sql", {"sql": "SELECT AVG(revenue) FROM sales WHERE date >= '2026-01-01'"}),
        ("aggregate_metric", {"metric": {"column": "revenue"}, "filters": [{"column": "order_date", "op": ">="}]}),
    ],
)
def test_period_applied_in_any_form_is_accepted(tool: str, args: dict) -> None:  # type: ignore[type-arg]
    ctx = ScopeContext("Average revenue per order for Enterprise customers in 2026?", data_years={"2025", "2026"})
    assert "missing_period" not in {i.kind for i in check_plan_scope(_plan(tool, args), ctx, "duckdb")}


def test_year_covering_all_data_needs_no_filter() -> None:
    ctx = ScopeContext("Total revenue for Enterprise customers in 2026?", data_years={"2026"})
    assert check_plan_scope(_plan("compute_metric", AOV), ctx, "duckdb") == []


def test_month_and_quarter_names_need_a_period_but_may_the_verb_does_not() -> None:
    args = {"metric": {"column": "revenue"}, "group_by": ["region"]}
    assert check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Top region in March?"), "duckdb")
    assert check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Top region in Q2?"), "duckdb")
    assert not check_plan_scope(_plan("aggregate_metric", args), ScopeContext("Which region may grow?"), "duckdb")


def test_lookup_only_plans_are_not_flagged() -> None:
    assert not check_plan_scope(_plan("list_tables", {}), ScopeContext("What tables cover 2026?"), "duckdb")
