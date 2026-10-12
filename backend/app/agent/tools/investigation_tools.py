"""Investigation tools: anomaly detection and driver (root-cause) exploration.

Driver analysis is descriptive decomposition. Its outputs are phrased as contributions and associations,
never as causes.
"""

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
    clip_to_data,
    complete_series,
    compact_table,
    filter_entities,
    filters_text,
    frame,
    metric_label,
    query,
    require_date_column,
    resolve_period,
)
from app.services.analytics import anomaly as anomalies
from app.services.analytics import stats
from app.services.analytics.querybuilder import MetricSpec

_SEASONAL = {"day": 7, "week": None, "month": 12, "quarter": 4}


class AnomalyInput(TableArgs):
    metric: MetricSpec
    date_column: str | None = None
    time_grain: Literal["day", "week", "month", "quarter"] | None = Field(
        None, description="Defaults to the date column's natural granularity")
    dimension: str | None = Field(None, description="Optional: also scan each segment of this dimension separately")
    method: Literal["auto", "zscore", "iqr", "rolling", "isolation_forest"] = "auto"
    threshold: float = Field(3.0, ge=1.5, le=6.0, description="z-score threshold for zscore/rolling methods")
    period: str | None = Field(None, description="Optional period to restrict the scan")


class DetectAnomalies(Tool):
    name = "detect_anomalies"
    description = ("Find unusual points in a metric over time (rolling baseline that accounts for weekly/seasonal "
                   "patterns, z-score, IQR or Isolation Forest). Optionally scans each segment of a dimension. "
                   "Each anomaly reports observed vs baseline value, deviation % and severity. Output columns: period, "
                   "segment, observed, baseline, deviation_pct, severity, method, direction; it also stores the "
                   "underlying series (period, value) for a line chart.")
    Input = AnomalyInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, AnomalyInput)
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        date_column = require_date_column(ctx, table, args.date_column)
        column_meta = next(c for c in table.columns if c.name.lower() == date_column.lower())
        natural = (column_meta.stats or {}).get("granularity", "daily")
        grain = args.time_grain or {"daily": "day", "intraday": "day", "weekly": "week", "monthly": "month",
                                    "quarterly": "quarter"}.get(natural, "day")
        projections: list[exp.Expression] = [qb.time_bucket(date_column, grain).as_("period")]
        group: list[exp.Expression] = [exp.column("period")]
        if args.dimension:
            projections.append(qb.col(args.dimension).as_("segment"))
            group.append(exp.column("segment"))
        projections.append(qb.metric_expr(args.metric).as_("value"))
        conditions = []
        period = None
        if args.period:
            period = resolve_period(ctx, table, args.period, date_column)
            conditions.append(qb.period_condition(date_column, period))
        sql = qb.select(projections, filters=args.filters, extra_conditions=conditions, group_by=group,
                        order_by=[exp.Ordered(this=exp.column("period"))])
        result, sql_id = query(ctx, sql, internal=True)
        data = frame(result)
        if data.empty:
            raise ToolError("empty_result", "No data for anomaly detection; check filters/period")
        label = metric_label(args.metric)
        found: list[anomalies.Anomaly] = []
        start, end = clip_to_data(table, date_column, *((period.start, period.end) if period else (None, None)))
        series_sets = [(None, complete_series(data.groupby("period")["value"].sum(), grain, args.metric.agg, start, end))]
        if args.dimension:
            series_sets += [(str(seg), complete_series(g.groupby("period")["value"].sum(), grain, args.metric.agg,
                                                       start, end))
                            for seg, g in data.groupby("segment")][:25]
        method_used = args.method
        for segment, series in series_sets:
            series = series.sort_index()
            dimension = args.dimension if segment else None
            if args.method in {"auto", "rolling"}:
                new = anomalies.detect_rolling(series, label, dimension, window=7 if grain == "day" else 4,
                                               threshold=args.threshold, seasonal_period=_SEASONAL.get(grain))
                method_used = "rolling"
            elif args.method == "zscore":
                new = anomalies.detect_zscore(series, label, dimension, args.threshold)
            elif args.method == "iqr":
                new = anomalies.detect_iqr(series, label, dimension)
            else:
                frame_ = pd.DataFrame({"value": series.values, "key": series.index})
                frame_["lag1"] = frame_["value"].shift(1).bfill()
                new = anomalies.detect_isolation_forest(frame_, "value", ["value", "lag1"], key_column="key",
                                                        dimension=dimension)
            for item in new:
                item.metric = f"{label} [{segment}]" if segment else label
            found += new
        ranked = [a for a in anomalies.rank(found, 25) if a.severity != "none"]
        findings: list[FindingDraft] = []
        rows: list[list[object]] = []
        for item in ranked:
            segment = item.metric.split("[", 1)[1].rstrip("]") if "[" in item.metric else None
            rows.append([item.key, segment, item.observed, item.baseline, item.deviation_pct, item.severity,
                         item.method, item.direction])
            where = f" for {args.dimension} = {segment}" if segment else ""
            findings.append(FindingDraft(
                kind="anomaly",
                statement=f"Anomaly ({item.severity}, {item.method}): {label}{where}{filters_text(args.filters)} in "
                          f"period {item.key} was {fmt_number(item.observed)} vs baseline "
                          f"{fmt_number(item.baseline)} ({fmt_pct(item.deviation_pct)}, {item.direction})",
                values={"observed": item.observed, "baseline": item.baseline, "deviation_pct": item.deviation_pct,
                        "score": item.score},
                formula=f"({fmt_number(item.observed)} - {fmt_number(item.baseline)}) / {fmt_number(item.baseline)} * 100",
                periods=[item.key], entities=[s for s in [segment] if s] + filter_entities(args.filters),
                payload={"severity": item.severity, "method": item.method, "dimension": args.dimension,
                         "segment": segment, "metric": label},
            ))
        if not ranked:
            findings.append(FindingDraft(kind="anomaly", statement=f"No anomalies above threshold {args.threshold} "
                                         f"were found in {label} at {grain} grain", values={"count": 0, "threshold": args.threshold}))
        columns = [{"name": n, "type": "str"} for n in ("period", "segment", "observed", "baseline", "deviation_pct",
                                                         "severity", "method", "direction")]
        stored = ctx.save_result_table(f"anomalies in {label}", columns, rows,
                                       source={"type": "sql", "sql_execution_id": sql_id, "sql": result.executed_sql,
                                               "method": method_used, "grain": grain})
        series_table = ctx.save_result_table(
            f"{label} by {grain}", [{"name": "period", "type": "date"}, {"name": "value", "type": "float"}],
            [[str(k)[:10], None if pd.isna(v) else float(v)] for k, v in series_sets[0][1].sort_index().items()],
            source={"type": "sql", "sql_execution_id": sql_id, "sql": result.executed_sql})
        high = sum(1 for a in ranked if a.severity == "high")
        return ToolResult(
            summary=f"result_id={stored.id} (series result_id={series_table.id}) grain={grain} anomalies={len(ranked)} "
                    f"high={high}\n{compact_table([c['name'] for c in columns], rows, 12)}",
            result_table_id=stored.id, findings=findings, data={"series_result_id": series_table.id},
            notable=high > 0)


class DriversInput(TableArgs):
    metric: MetricSpec
    current_period: str
    previous_period: str
    dimensions: list[str] = Field(default_factory=list, description="Dimensions to test; default: all low-cardinality")
    quantity_column: str | None = Field(None, description="Optional units column for a price/volume decomposition")
    date_column: str | None = None


class IdentifyDrivers(Tool):
    name = "identify_drivers"
    description = ("Explain a change in an additive metric between two periods: for each dimension, which segments "
                   "contributed most to the change (contribution analysis), which dimension concentrates the change, "
                   "and optionally a volume vs price/mix decomposition. Results describe contributions, not causes. "
                   "Output columns: dimension, segment, previous, current, change, pct_change, contribution_pct.")
    Input = DriversInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, DriversInput)
        if args.metric.agg not in {"sum", "count"}:
            raise ToolError("invalid_arguments", "identify_drivers needs an additive metric (agg 'sum' or 'count')")
        table = ctx.table(args.table)
        qb = builder(ctx, table)
        date_column = require_date_column(ctx, table, args.date_column)
        current = resolve_period(ctx, table, args.current_period, date_column)
        previous = resolve_period(ctx, table, args.previous_period, date_column)
        dims = args.dimensions or [
            c.name for c in table.columns
            if c.role == "dimension" and 1 < int((c.stats or {}).get("distinct_count") or 0) <= 60 and not c.is_pii][:8]
        if not dims:
            raise ToolError("invalid_arguments", "No dimensions available to break the change down")
        label = metric_label(args.metric)
        case = exp.Case().when(qb.period_condition(date_column, current), exp.Literal.string("current")).when(
            qb.period_condition(date_column, previous), exp.Literal.string("previous"))
        either = exp.or_(qb.period_condition(date_column, current), qb.period_condition(date_column, previous))
        findings: list[FindingDraft] = []
        rows: list[list[object]] = []
        ranking: list[tuple[float, str, dict[str, object]]] = []
        total_prev = total_curr = 0.0
        sql_ids: list[str] = []
        entities = filter_entities(args.filters)
        for dim in dims:
            sql = qb.select([case.as_("slot"), qb.col(dim).as_("segment"), qb.metric_expr(args.metric).as_("value")],
                            filters=args.filters, extra_conditions=[either],
                            group_by=[exp.column("slot"), exp.column("segment")])
            result, sql_id = query(ctx, sql, internal=True)
            sql_ids.append(sql_id)
            data = frame(result)
            if data.empty:
                continue
            pivot = data.pivot_table(index="segment", columns="slot", values="value", aggfunc="sum").fillna(0)
            prev = pivot["previous"].to_dict() if "previous" in pivot else {}
            curr = pivot["current"].to_dict() if "current" in pivot else {}
            total_prev, total_curr = sum(prev.values()), sum(curr.values())
            contributions = stats.contribution(prev, curr)
            total_change = total_curr - total_prev
            # Concentration: share of the total change explained by the single largest same-direction segment.
            same_dir = [c for c in contributions if (c["change"] or 0) * total_change > 0]
            top = max(same_dir, key=lambda c: abs(c["change"] or 0), default=None)
            score = abs(top["contribution_pct"] or 0) if top else 0.0
            ranking.append((score, dim, top or {}))
            for item in contributions:
                rows.append([dim, item["segment"], item["previous"], item["current"], item["change"],
                             item["pct_change"], item["contribution_pct"]])
            for item in sorted(contributions, key=lambda c: abs(c["change"] or 0), reverse=True)[:3]:
                findings.append(FindingDraft(
                    kind="driver",
                    statement=f"{dim} = {item['segment']}: {label} went from {fmt_number(item['previous'])} "
                              f"({previous.label}) to {fmt_number(item['current'])} ({current.label}), change "
                              f"{fmt_number(item['change'])} ({fmt_pct(item['pct_change'])}), "
                              f"{fmt_number(item['contribution_pct'])}% of the total change",
                    values={"previous": item["previous"], "current": item["current"], "change": item["change"],
                            "pct_change": item["pct_change"], "contribution_pct": item["contribution_pct"]},
                    formula=f"contribution = {fmt_number(item['change'])} / {fmt_number(total_change)} * 100",
                    periods=[previous.label, current.label], entities=[str(item["segment"]), *entities],
                    payload={"dimension": dim, "segment": str(item["segment"])}))
        total_change = total_curr - total_prev
        pct = stats.pct_change(total_prev, total_curr)
        findings.insert(0, FindingDraft(
            kind="comparison",
            statement=f"{label}{filters_text(args.filters)}: {previous.label} = {fmt_number(total_prev)}, "
                      f"{current.label} = {fmt_number(total_curr)}, change {fmt_number(total_change)} ({fmt_pct(pct)})",
            values={"previous": total_prev, "current": total_curr, "change": total_change, "pct_change": pct},
            formula=f"({fmt_number(total_curr)} - {fmt_number(total_prev)}) / {fmt_number(total_prev)} * 100",
            periods=[previous.label, current.label], entities=entities))
        ranking.sort(key=lambda r: -r[0])
        if ranking and ranking[0][2]:
            score, dim, top = ranking[0]
            findings.append(FindingDraft(
                kind="driver",
                statement=f"The change is most concentrated in dimension {dim}: segment {top.get('segment')} alone "
                          f"accounts for {fmt_number(score)}% of the total change (largest contributor; association, "
                          "not proven cause)",
                values={"contribution_pct": score}, entities=[str(top.get("segment")), dim],
                periods=[previous.label, current.label]))
        if args.quantity_column:
            qty = MetricSpec(column=args.quantity_column, agg="sum")
            sql = qb.select([case.as_("slot"), qb.metric_expr(args.metric).as_("value"),
                             qb.metric_expr(qty).as_("qty")], filters=args.filters, extra_conditions=[either],
                            group_by=[exp.column("slot")])
            result, sql_id = query(ctx, sql, internal=True)
            sql_ids.append(sql_id)
            agg = frame(result).set_index("slot")
            if {"previous", "current"} <= set(agg.index) and agg.loc["previous", "qty"] and agg.loc["current", "qty"]:
                q0, q1 = float(agg.loc["previous", "qty"]), float(agg.loc["current", "qty"])
                p0, p1 = float(agg.loc["previous", "value"]) / q0, float(agg.loc["current", "value"]) / q1
                dec = stats.price_volume_decomposition(q0, p0, q1, p1)
                findings.append(FindingDraft(
                    kind="driver",
                    statement=f"Decomposition of the {label} change: volume ({args.quantity_column}) "
                              f"{fmt_number(q0)} -> {fmt_number(q1)} ({fmt_pct(dec['volume_pct_change'])}) contributes "
                              f"{fmt_number(dec['volume_effect'])}; average value per unit {fmt_number(p0)} -> "
                              f"{fmt_number(p1)} ({fmt_pct(dec['avg_price_pct_change'])}) contributes "
                              f"{fmt_number(dec['price_effect'])}",
                    values={k: v for k, v in dec.items() if v is not None},
                    formula="volume_effect = (q1 - q0) * p0; price_effect = (p1 - p0) * q1",
                    periods=[previous.label, current.label], entities=entities))
        columns = [{"name": n, "type": "str" if n in {"dimension", "segment"} else "float"}
                   for n in ("dimension", "segment", "previous", "current", "change", "pct_change", "contribution_pct")]
        stored = ctx.save_result_table(f"drivers of {label}: {current.label} vs {previous.label}", columns, rows,
                                       source={"type": "sql", "sql_execution_ids": sql_ids,
                                               "periods": [previous.as_dict(), current.as_dict()]})
        ranking_text = ", ".join(f"{d} (top segment {t.get('segment')}: {s:.1f}% of change)" for s, d, t in ranking)
        top_rows = sorted(rows, key=lambda r: abs(float(r[4] or 0)), reverse=True)[:12]
        return ToolResult(
            summary=f"result_id={stored.id}\ntotal: {fmt_number(total_prev)} -> {fmt_number(total_curr)} ({fmt_pct(pct)})"
                    f"\ndimension concentration: {ranking_text}\n{compact_table([c['name'] for c in columns], top_rows)}",
            result_table_id=stored.id, findings=findings, notable=True)
