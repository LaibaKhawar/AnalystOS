"""Deterministic metric tools: aggregation, period comparison, segments, statistics, correlation."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field
from sqlglot import exp

from app.agent.context import ToolContext, fmt_number, fmt_pct
from app.agent.tools.base import FindingDraft, Tool, ToolError, ToolResult
from app.agent.tools.common import (
    TableArgs,
    builder,
    compact_table,
    filter_entities,
    filters_text,
    frame,
    metric_label,
    query,
    ranking_findings,
    require_date_column,
    resolve_period,
    series_findings,
)
from app.services.analytics import stats
from app.services.analytics.querybuilder import MetricSpec

Grain = Literal["day", "week", "month", "quarter", "year"]


class AggregateInput(TableArgs):
    metric: MetricSpec = Field(..., description="What to measure, e.g. {column: 'revenue', agg: 'sum'}")
    group_by: list[str] = Field(default_factory=list, description="Dimension columns to group by (max 2)")
    time_grain: Grain | None = Field(None, description="Bucket a date column by this grain to get a time series")
    date_column: str | None = None
    period: str | None = Field(None, description="Restrict to a period, e.g. '2026-Q3', '2026-07', '2026'")
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(50, ge=1, le=500)


class AggregateMetric(Tool):
    name = "aggregate_metric"
    description = (
        "Compute a metric (sum/avg/count/count_distinct/min/max/median of a column) overall, by "
        "dimension(s), and/or over time (time_grain). Use for totals, rankings ('which region is highest'), "
        "and trends (monthly revenue). Period-over-period changes are computed for time series. Output columns: "
        "'period' (when time_grain is set), the group_by columns, and the metric named after its column "
        "for sum (e.g. 'revenue') or '<agg>_<column>' otherwise ('avg_price', 'row_count')."
    )
    Input = AggregateInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, AggregateInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        if len(args.group_by) > 2:
            raise ToolError("invalid_arguments", "group_by supports at most 2 columns")
        projections: list[exp.Expr] = []
        group: list[exp.Expr] = []
        conditions: list[exp.Expr] = []
        date_column = None
        if args.time_grain or args.period:
            date_column = require_date_column(ctx, table, args.date_column)
        if args.time_grain:
            assert date_column
            projections.append(qb.time_bucket(date_column, args.time_grain).as_("period"))
            group.append(exp.column("period"))
        for dim in args.group_by:
            projections.append(qb.col(dim))
            group.append(qb.col(dim))
        value_label = args.metric.label()
        projections.append(qb.metric_expr(args.metric).as_(value_label))
        period = None
        if args.period:
            assert date_column
            period = resolve_period(ctx, table, args.period, date_column)
            conditions.append(qb.period_condition(date_column, period))
        if args.time_grain:
            order: list[exp.Expr] = [exp.Ordered(this=exp.column("period"))]
        elif group:
            order = [exp.Ordered(this=exp.column(value_label), desc=args.order == "desc")]
        else:
            order = []
        sql = qb.select(
            projections,
            filters=args.filters,
            extra_conditions=conditions,
            group_by=group or None,
            order_by=order or None,
            # Rankings keep the full context ("rank 1 of 5", a chartable result) even when asked for the top 1.
            limit=max(args.limit, 25) if group and not args.time_grain else None,
        )
        result, sql_id = query(ctx, sql, internal=bool(args.time_grain))
        names = [c["name"] for c in result.columns]
        data = frame(result)
        label = metric_label(args.metric)
        context = filters_text(args.filters) + (f" in {period.label}" if period else "")
        periods = [period.label] if period else []
        entities = filter_entities(args.filters)
        findings: list[FindingDraft] = []
        if not group:
            value = data.iloc[0, 0] if not data.empty else None
            findings.append(
                FindingDraft(
                    kind="value",
                    statement=f"{label}{context}: {fmt_number(value)}",
                    values={"value": value},
                    periods=periods,
                    entities=entities,
                )
            )
        elif args.time_grain and not args.group_by:
            from app.agent.tools.common import clip_to_data, complete_series

            start, end = clip_to_data(
                table, date_column, period.start if period else None, period.end if period else None
            )
            completed = complete_series(
                data.set_index("period")[value_label], args.time_grain, args.metric.agg, start, end
            )
            data = completed.rename(value_label).rename_axis("period").reset_index()
            result.rows = [[p, None if pd.isna(v) else float(v)] for p, v in data.itertuples(index=False)]
            findings = series_findings(
                data,
                "period",
                value_label,
                label,
                context=filters_text(args.filters),
                entities=entities,
                additive=args.metric.agg in {"sum", "count"},
            )
        elif not args.time_grain and len(args.group_by) == 1:
            findings = ranking_findings(
                data, args.group_by[0], value_label, label, context=context, periods=periods, extra_entities=entities
            )
        else:
            from app.agent.tools.common import rows_findings

            findings = rows_findings(f"{label}{context}", names, result.rows, limit=40)
        stored = ctx.save_result_table(
            f"{label} by {', '.join(([args.time_grain] if args.time_grain else []) + args.group_by) or 'total'}",
            result.columns,
            result.rows,
            truncated=result.truncated,
            source={
                "type": "sql",
                "sql_execution_id": sql_id,
                "sql": result.executed_sql,
                "filters": [f.model_dump() for f in args.filters],
                "period": period.as_dict() if period else None,
            },
        )
        return ToolResult(
            summary=f"result_id={stored.id}\n{compact_table(names, result.rows, 24)}",
            data={"row_count": result.row_count},
            result_table_id=stored.id,
            findings=findings,
        )


class ComparePeriodsInput(TableArgs):
    metric: MetricSpec
    current_period: str = Field(..., description="e.g. '2026-Q3'")
    previous_period: str = Field(..., description="e.g. '2026-Q2'")
    dimension: str | None = Field(None, description="Optional: break the change down by this dimension")
    date_column: str | None = None


class ComparePeriods(Tool):
    name = "compare_periods"
    description = (
        "Compare a metric between two periods (e.g. Q3 vs Q2, 2026-04 vs 2026-03): previous, current, "
        "absolute and % change. With `dimension`, also the change per segment and each segment's "
        "contribution to the total change. Output columns: <dimension or 'segment'>, previous, current, "
        "change, pct_change, contribution_pct."
    )
    Input = ComparePeriodsInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ComparePeriodsInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        date_column = require_date_column(ctx, table, args.date_column)
        current = resolve_period(ctx, table, args.current_period, date_column)
        previous = resolve_period(ctx, table, args.previous_period, date_column)
        label = metric_label(args.metric)
        value = qb.metric_expr(args.metric)
        case = (
            exp.Case()
            .when(qb.period_condition(date_column, current), exp.Literal.string("current"))
            .when(qb.period_condition(date_column, previous), exp.Literal.string("previous"))
        )
        projections: list[exp.Expr] = [case.as_("period_slot")]
        group: list[exp.Expr] = [exp.column("period_slot")]
        if args.dimension:
            projections.append(qb.col(args.dimension).as_("segment"))
            group.append(exp.column("segment"))
        projections.append(value.as_("value"))
        either = exp.or_(qb.period_condition(date_column, current), qb.period_condition(date_column, previous))
        sql = qb.select(projections, filters=args.filters, extra_conditions=[either], group_by=group)
        result, sql_id = query(ctx, sql, internal=True)
        data = frame(result)
        entities = filter_entities(args.filters)
        context = filters_text(args.filters)
        totals = data.groupby("period_slot")["value"].sum() if not data.empty else pd.Series(dtype=float)
        prev_total = float(totals.get("previous", 0.0) or 0.0)
        curr_total = float(totals.get("current", 0.0) or 0.0)
        if args.metric.agg in {"avg", "median", "min", "max", "count_distinct"} and args.dimension:
            # Non-additive metrics: overall value must be computed without the dimension split.
            overall_sql = qb.select(
                [case.as_("period_slot"), value.as_("value")],
                filters=args.filters,
                extra_conditions=[either],
                group_by=[exp.column("period_slot")],
            )
            overall, _ = query(ctx, overall_sql, internal=True)
            o = frame(overall).set_index("period_slot")["value"]
            prev_total, curr_total = float(o.get("previous", 0.0) or 0.0), float(o.get("current", 0.0) or 0.0)
        change = curr_total - prev_total
        pct = stats.pct_change(prev_total, curr_total)
        findings = [
            FindingDraft(
                kind="comparison",
                statement=f"{label}{context}: {previous.label} = {fmt_number(prev_total)}, {current.label} = "
                f"{fmt_number(curr_total)}, change {fmt_number(change)} ({fmt_pct(pct)})",
                values={"previous": prev_total, "current": curr_total, "change": change, "pct_change": pct},
                formula=f"({fmt_number(curr_total)} - {fmt_number(prev_total)}) / {fmt_number(prev_total)} * 100",
                periods=[previous.label, current.label],
                entities=entities,
                payload={"previous_period": previous.as_dict(), "current_period": current.as_dict()},
            )
        ]
        rows: list[list[object]] = []
        columns = [
            {"name": n, "type": t}
            for n, t in (
                (args.dimension or "segment", "str"),
                ("previous", "float"),
                ("current", "float"),
                ("change", "float"),
                ("pct_change", "float"),
                ("contribution_pct", "float"),
            )
        ]
        if args.dimension and not data.empty:
            pivot = data.pivot_table(index="segment", columns="period_slot", values="value", aggfunc="sum").fillna(0)
            prev_map = {str(k): float(v) for k, v in pivot["previous"].items()} if "previous" in pivot else {}
            curr_map = {str(k): float(v) for k, v in pivot["current"].items()} if "current" in pivot else {}
            additive = args.metric.agg in {"sum", "count"}
            contributions = stats.contribution(prev_map, curr_map)
            for item in contributions:
                contribution = item["contribution_pct"] if additive else None
                rows.append(
                    [
                        item["segment"],
                        item["previous"],
                        item["current"],
                        item["change"],
                        item["pct_change"],
                        contribution,
                    ]
                )
            ordered = sorted(contributions, key=lambda r: abs(r["change"] or 0), reverse=True)
            for item in ordered[:15]:
                contribution = item["contribution_pct"] if additive else None
                findings.append(
                    FindingDraft(
                        kind="comparison",
                        statement=f"{label} for {args.dimension} = {item['segment']}{context}: {previous.label} = "
                        f"{fmt_number(item['previous'])}, {current.label} = {fmt_number(item['current'])}, "
                        f"change {fmt_number(item['change'])} ({fmt_pct(item['pct_change'])})"
                        + (f"; {fmt_number(contribution)}% of the total change" if contribution is not None else ""),
                        values={
                            "previous": item["previous"],
                            "current": item["current"],
                            "change": item["change"],
                            "pct_change": item["pct_change"],
                            "contribution_pct": contribution,
                        },
                        formula=f"({fmt_number(item['current'])} - {fmt_number(item['previous'])}) / "
                        f"{fmt_number(item['previous'])} * 100",
                        periods=[previous.label, current.label],
                        entities=[str(item["segment"]), *entities],
                        payload={"dimension": args.dimension, "segment": str(item["segment"])},
                    )
                )
        else:
            rows = [["total", prev_total, curr_total, change, pct, 100.0 if change else None]]
        stored = ctx.save_result_table(
            f"{label}: {current.label} vs {previous.label}" + (f" by {args.dimension}" if args.dimension else ""),
            columns,
            rows,
            source={
                "type": "sql",
                "sql_execution_id": sql_id,
                "sql": result.executed_sql,
                "periods": [previous.as_dict(), current.as_dict()],
                "filters": [f.model_dump() for f in args.filters],
            },
        )
        summary = (
            f"result_id={stored.id}\n{label}{context}: {previous.label}={fmt_number(prev_total)} "
            f"{current.label}={fmt_number(curr_total)} change={fmt_number(change)} ({fmt_pct(pct)})"
        )
        if rows and args.dimension:
            summary += "\n" + compact_table([c["name"] for c in columns], rows, 15)
        if prev_total == 0 and curr_total == 0:
            summary += "\nBoth periods are empty: check the period labels against the date range in the schema."
        return ToolResult(
            summary=summary,
            result_table_id=stored.id,
            findings=findings,
            data={"previous": prev_total, "current": curr_total, "pct_change": pct},
            notable=pct is not None and abs(pct) >= 10,
        )


class SegmentsInput(TableArgs):
    metric: MetricSpec
    dimension: str
    period: str | None = None
    date_column: str | None = None
    top_n: int = Field(15, ge=1, le=100)


class AnalyzeSegments(Tool):
    name = "analyze_segments"
    description = (
        "Break a metric down by one dimension: value, share of total, rank, row count and average per "
        "row for each segment; flags concentration (top segment share). Output columns: <dimension>, "
        "<metric name>, share_pct, row_count, avg_per_row."
    )
    Input = SegmentsInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, SegmentsInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        conditions = []
        period = None
        if args.period:
            date_column = require_date_column(ctx, table, args.date_column)
            period = resolve_period(ctx, table, args.period, date_column)
            conditions.append(qb.period_condition(date_column, period))
        value_label = "value"
        sql = qb.select(
            [
                qb.col(args.dimension).as_("segment"),
                qb.metric_expr(args.metric).as_(value_label),
                exp.Count(this=exp.Star()).as_("row_count"),
            ],
            filters=args.filters,
            extra_conditions=conditions,
            group_by=[exp.column("segment")],
            order_by=[exp.Ordered(this=exp.column(value_label), desc=True)],
        )
        result, sql_id = query(ctx, sql, internal=True)
        data = frame(result)
        if data.empty:
            raise ToolError("empty_result", "No rows matched; check filters and period")
        total = float(pd.to_numeric(data["value"], errors="coerce").sum())
        data["share_pct"] = data["value"] / total * 100 if total else None
        data["avg_per_row"] = data["value"] / data["row_count"].where(data["row_count"] != 0)
        label = metric_label(args.metric)
        context = filters_text(args.filters) + (f" in {period.label}" if period else "")
        findings = ranking_findings(
            data.rename(columns={"segment": args.dimension}),
            args.dimension,
            "value",
            label,
            context=context,
            periods=[period.label] if period else [],
            limit=args.top_n,
            extra_entities=filter_entities(args.filters),
        )
        top_share = float(data["share_pct"].iloc[0]) if total else None
        if top_share is not None and len(data) > 1:
            findings.append(
                FindingDraft(
                    kind="stat",
                    statement=f"The top {args.dimension} ({data['segment'].iloc[0]}) accounts for "
                    f"{top_share:.2f}% of {label}{context}",
                    values={"share_pct": top_share, "segments": len(data)},
                    entities=[str(data["segment"].iloc[0])],
                    formula=f"{fmt_number(data['value'].iloc[0])} / {fmt_number(total)} * 100",
                )
            )
        rows = data[["segment", "value", "share_pct", "row_count", "avg_per_row"]].values.tolist()
        value_name = args.metric.label() if args.metric.label() != args.dimension else "value"
        columns = [
            {"name": n, "type": "float" if n != args.dimension else "str"}
            for n in (args.dimension, value_name, "share_pct", "row_count", "avg_per_row")
        ]
        stored = ctx.save_result_table(
            f"{label} by {args.dimension}",
            columns,
            rows,
            source={"type": "sql", "sql_execution_id": sql_id, "sql": result.executed_sql},
        )
        return ToolResult(
            summary=f"result_id={stored.id}\n{compact_table([c['name'] for c in columns], rows, 20)}",
            result_table_id=stored.id,
            findings=findings,
        )


class StatisticsInput(TableArgs):
    column: str
    group_by: str | None = Field(None, description="Optional dimension: statistics per group (and a test if 2 groups)")
    period: str | None = None
    date_column: str | None = None


class ComputeStatistics(Tool):
    name = "compute_statistics"
    description = (
        "Descriptive statistics for a numeric column (count, mean, median, std, variance, quantiles, "
        "95% confidence interval), optionally per group; with exactly two groups also runs Welch's t-test "
        "and Mann-Whitney U."
    )
    Input = StatisticsInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, StatisticsInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        if not qb.is_numeric(args.column):
            raise ToolError("type_error", f"Column '{args.column}' is not numeric")
        conditions = []
        period = None
        if args.period:
            date_column = require_date_column(ctx, table, args.date_column)
            period = resolve_period(ctx, table, args.period, date_column)
            conditions.append(qb.period_condition(date_column, period))
        projections = [qb.col(args.column).as_("x")]
        if args.group_by:
            meta = next((c for c in table.columns if c.name.lower() == args.group_by.lower()), None)
            if meta is not None and int((meta.stats or {}).get("distinct_count") or 0) > 50:
                raise ToolError(
                    "invalid_arguments",
                    f"'{args.group_by}' has too many distinct values to group by; choose a dimension column",
                )
            projections.insert(0, qb.col(args.group_by).as_("g"))
        sql = qb.select(projections, filters=args.filters, extra_conditions=conditions)
        result, sql_id = query(ctx, sql, internal=True)
        data = frame(result)
        context = filters_text(args.filters) + (f" in {period.label}" if period else "")
        findings: list[FindingDraft] = []
        rows: list[list[object]] = []
        keys = ["count", "mean", "median", "std", "variance", "min", "q1", "q3", "max", "ci_low", "ci_high"]
        groups = (
            [("all", data["x"])]
            if not args.group_by
            else [(str(k), g["x"]) for k, g in list(data.groupby("g", dropna=False))[:30]]
        )
        for name, series in groups:
            desc = stats.describe(series)
            rows.append([name] + [desc.get(k) for k in keys])
            subject = args.column if name == "all" else f"{args.column} for {args.group_by} = {name}"
            findings.append(
                FindingDraft(
                    kind="stat",
                    statement=f"{subject}{context}: n={fmt_number(desc.get('count'))}, "
                    f"mean={fmt_number(desc.get('mean'))}, "
                    f"median={fmt_number(desc.get('median'))}, std={fmt_number(desc.get('std'))}, "
                    f"95% CI of mean [{fmt_number(desc.get('ci_low'))}, {fmt_number(desc.get('ci_high'))}]",
                    values={k: desc.get(k) for k in keys if desc.get(k) is not None},
                    entities=[name] if name != "all" else [],
                    periods=[period.label] if period else [],
                )
            )
        summary_extra = ""
        if args.group_by and len(groups) == 2:
            test = stats.compare_groups(groups[0][1], groups[1][1])
            findings.append(
                FindingDraft(
                    kind="stat",
                    statement=f"Difference in mean {args.column} between {groups[0][0]} and {groups[1][0]}{context}: "
                    f"{fmt_number(test.get('mean_diff'))}; Welch t-test p={test.get('welch_p')}, "
                    f"Mann-Whitney p={test.get('mann_whitney_p')}"
                    + (
                        " (statistically significant at 5%)"
                        if test.get("significant")
                        else " (not statistically significant at 5%)"
                    ),
                    values={k: v for k, v in test.items() if isinstance(v, int | float) and not isinstance(v, bool)},
                    entities=[groups[0][0], groups[1][0]],
                )
            )
            summary_extra = f"\ngroup test: {test}"
        columns = [{"name": "group", "type": "str"}] + [{"name": k, "type": "float"} for k in keys]
        stored = ctx.save_result_table(
            f"statistics of {args.column}",
            columns,
            rows,
            source={"type": "sql", "sql_execution_id": sql_id, "sql": result.executed_sql},
        )
        return ToolResult(
            summary=f"result_id={stored.id}\n{compact_table([c['name'] for c in columns], rows)}" + summary_extra,
            result_table_id=stored.id,
            findings=findings,
        )


class CorrelationInput(TableArgs):
    columns: list[str] = Field(..., min_length=2, max_length=8, description="Numeric columns to correlate")
    method: Literal["pearson", "spearman"] = "pearson"
    aggregate_by: str | None = Field(
        None,
        description="Optional: first sum the columns per value of this column "
        "(e.g. a date or customer) and correlate the aggregates",
    )


class CalculateCorrelation(Tool):
    name = "calculate_correlation"
    description = (
        "Pairwise correlation (Pearson or Spearman) between numeric columns with p-values and sample "
        "size. Correlation is association only and never evidence of causation."
    )
    Input = CorrelationInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, CorrelationInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        for column in args.columns:
            if not qb.is_numeric(column):
                raise ToolError("type_error", f"Column '{column}' is not numeric")
        if args.aggregate_by:
            projections = [qb.col(args.aggregate_by).as_("k")] + [exp.Sum(this=qb.col(c)).as_(c) for c in args.columns]
            sql = qb.select(projections, filters=args.filters, group_by=[exp.column("k")])
        else:
            sql = qb.select([qb.col(c) for c in args.columns], filters=args.filters)
        result, sql_id = query(ctx, sql, internal=True)
        data = frame(result)
        rows: list[list[object]] = []
        findings: list[FindingDraft] = []
        for i, a in enumerate(args.columns):
            for b in args.columns[i + 1 :]:
                res = stats.correlation(data[a], data[b], args.method)
                rows.append([a, b, res["coefficient"], res["p_value"], res["n"], res["strength"]])
                findings.append(
                    FindingDraft(
                        kind="correlation",
                        statement=f"{args.method.title()} correlation between {a} and {b}"
                        + (f" (aggregated by {args.aggregate_by})" if args.aggregate_by else "")
                        + f": r={res['coefficient']} ({res['strength']}), p={res['p_value']}, n={res['n']}. "
                        "Association only, not causation.",
                        values={"coefficient": res["coefficient"], "p_value": res["p_value"], "n": res["n"]},
                        entities=[a, b],
                    )
                )
        columns = [
            {"name": n, "type": t}
            for n, t in (
                ("var_x", "str"),
                ("var_y", "str"),
                ("coefficient", "float"),
                ("p_value", "float"),
                ("n", "int"),
                ("strength", "str"),
            )
        ]
        stored = ctx.save_result_table(
            "correlations",
            columns,
            rows,
            source={"type": "sql", "sql_execution_id": sql_id, "sql": result.executed_sql},
        )
        return ToolResult(
            summary=f"result_id={stored.id}\n{compact_table([c['name'] for c in columns], rows)}",
            result_table_id=stored.id,
            findings=findings,
        )
