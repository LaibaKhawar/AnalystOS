"""Charts, evidence lookup, prior-analysis retrieval and report requests."""

from __future__ import annotations

from typing import Literal

from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.agent.context import ToolContext
from app.agent.tools.base import Tool, ToolError, ToolResult
from app.db.models import Analysis, AnalysisMemory, Chart, Finding
from app.services.viz.charts import ChartSpecError, build_chart, data_hash


class ChartInput(BaseModel):
    @field_validator("y", mode="before")
    @classmethod
    def _listify(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    result_id: str = Field(..., description="result_id of an earlier step (or '$<step id>')")
    chart_type: Literal["line", "bar", "stacked_bar", "scatter", "histogram", "box", "heatmap", "area"]
    x: str = Field(..., description="Column for the x axis (category, period, or numeric for scatter/histogram)")
    y: list[str] = Field(default_factory=list, description="Value column(s)")
    series: str | None = Field(None, description="Optional column that splits lines/bars into series")
    title: str
    interpretation: str | None = Field(None, description="One sentence on what the chart shows (no new numbers)")


class CreateChart(Tool):
    name = "create_chart"
    description = ("Create a chart from an earlier result table. Line for time trends, bar for category "
                   "comparisons, stacked_bar for composition, scatter for two numeric variables, histogram for a "
                   "distribution, box for spread/outliers by group, heatmap for a matrix.")
    Input = ChartInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ChartInput)
        source = ctx.get_result_table(args.result_id)
        names = [c["name"] for c in source.columns]
        x, y, series, notes = args.x, [c for c in args.y if c in names], args.series, []
        if args.series and args.series not in names:
            series = None
            notes.append(f"series '{args.series}' not in result; ignored")
        if args.y and not y:
            notes.append(f"y {args.y} not in result; using numeric columns")
        if x not in names:
            from app.services.viz.charts import recommend_type

            choice = recommend_type(source.columns, source.rows)
            if choice is None:
                raise ToolError("invalid_chart", f"Column '{x}' is not in the result", {"columns": names})
            notes.append(f"x '{x}' not in result; using '{choice[1]}'")
            x = choice[1]
            y = y or choice[2]
        if not y and args.chart_type not in {"histogram"}:
            numeric = [c["name"] for c in source.columns if c["name"] != x and
                       any(t in str(c.get("type", "")).upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC"))]
            y = numeric[:1]
        try:
            spec, data = build_chart(args.chart_type, source.columns, source.rows, x=x, y=y,
                                     series=series, title=args.title)
        except ChartSpecError as exc:
            raise ToolError("invalid_chart", str(exc), {"columns": [c["name"] for c in source.columns]}) from exc
        spec["args"] = {"x": x, "y": y, "series": series}
        if notes:
            spec["adjustments"] = notes
        spec["source"] = {"result_id": source.id, "name": source.name, **{k: v for k, v in source.source.items()
                                                                          if k in {"sql", "filters", "period", "periods"}}}
        chart = Chart(analysis_id=ctx.analysis_id, tool_execution_id=ctx.current_execution_id,
                      result_table_id=source.id, title=args.title[:300], chart_type=args.chart_type, spec=spec,
                      data=data, data_hash=data_hash(data), interpretation=args.interpretation)
        ctx.db.add(chart)
        ctx.db.flush()
        return ToolResult(summary=f"chart_id={chart.id} ({args.chart_type}, {len(data)} points) from {source.id}"
                                  + (f"; adjusted: {'; '.join(notes)}" if notes else ""),
                          chart_ids=[chart.id], data={"chart_id": chart.id})


class EvidenceInput(BaseModel):
    labels: list[str] = Field(default_factory=list, description="Finding labels such as F3; empty = all")


class RetrieveEvidence(Tool):
    name = "retrieve_evidence"
    description = "Look up findings recorded so far in this analysis (statement, values, formula, source)."
    Input = EvidenceInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, EvidenceInput)
        wanted = {label.upper() for label in args.labels}
        items = [f for f in ctx.findings if not wanted or f.label.upper() in wanted]
        return ToolResult(summary="\n".join(f"{f.label}: {f.statement}" for f in items[:60]) or "No findings yet",
                          data={"findings": [{"label": f.label, "statement": f.statement, "values": f.values,
                                              "formula": f.formula} for f in items[:60]]})


class PreviousInput(BaseModel):
    query: str = Field(..., description="What earlier analysis to look for")
    limit: int = Field(3, ge=1, le=5)


class RetrievePreviousAnalysis(Tool):
    name = "retrieve_previous_analysis"
    description = ("Search earlier completed analyses of this data source (semantic search). Returns their summaries "
                   "as background only: re-compute any number before stating it.")
    Input = PreviousInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, PreviousInput)
        from app.agent.llm.openai_compat import get_provider

        vector = None
        embeddings = get_provider().embed([args.query])
        if embeddings:
            vector = embeddings[0]
        stmt = select(AnalysisMemory, Analysis).join(Analysis, Analysis.id == AnalysisMemory.analysis_id).where(
            AnalysisMemory.user_id == ctx.user_id, AnalysisMemory.data_source_id == ctx.source.id,
            AnalysisMemory.analysis_id != ctx.analysis_id)
        if vector is not None:
            stmt = stmt.where(AnalysisMemory.embedding.is_not(None)).order_by(
                AnalysisMemory.embedding.cosine_distance(vector))
        else:
            terms = [t for t in args.query.lower().split() if len(t) > 3][:5]
            for term in terms:
                stmt = stmt.where(AnalysisMemory.content.ilike(f"%{term}%"))
            stmt = stmt.order_by(AnalysisMemory.created_at.desc())
        rows = ctx.db.execute(stmt.limit(args.limit)).all()
        if not rows:
            return ToolResult(summary="No earlier analyses matched.")
        lines = [f"[{a.created_at:%Y-%m-%d}] Q: {a.question}\n  summary: {m.content[:600]}" for m, a in rows]
        return ToolResult(summary="Background only (numbers must be recomputed):\n" + "\n".join(lines),
                          data={"analysis_ids": [a.id for _, a in rows]})


class ReportInput(BaseModel):
    title: str | None = None


class GenerateReport(Tool):
    name = "generate_report"
    description = ("Request a downloadable business report for this analysis. It is assembled after verification "
                   "from verified claims, charts and evidence. Include this step only when the user asks for a report.")
    Input = ReportInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ReportInput)
        ctx.report_requested = True
        ctx.report_title = args.title
        return ToolResult(summary="A report will be generated from the verified findings after synthesis.")


def findings_for(ctx: ToolContext) -> list[Finding]:
    return ctx.findings
