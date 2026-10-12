"""Persist verified claims + evidence, update conversation state, and store retrievable memory."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.verifier import VerificationReport
from app.core.logging import get_logger
from app.core.metrics import CLAIMS_VERIFIED
from app.db.models import (
    Analysis,
    AnalysisMemory,
    Chart,
    Claim,
    Conversation,
    Evidence,
    Finding,
    ResultTable,
    ToolExecution,
)
from app.services.viz.charts import build_chart, data_hash

log = get_logger(__name__)
_SOURCE_TYPES = {"sql": "sql_query", "python": "python"}


def persist_claims(db: Session, analysis: Analysis, report: VerificationReport, findings: list[Finding]) -> list[Claim]:
    by_id = {f.id: f for f in findings}
    by_label = {f.label: f for f in findings}
    created: list[Claim] = []
    for ordinal, check in enumerate(report.claims):
        claim = Claim(
            analysis_id=analysis.id,
            ordinal=ordinal,
            section=check.section,
            kind=check.kind,
            text=check.text,
            original_text=check.original_text,
            status=check.status,
            numbers=check.numbers,
            verification={
                "matches": [m.__dict__ for m in check.matches],
                "unsupported": check.unsupported,
                "notes": check.notes,
                "citations": check.citations,
            },
        )
        CLAIMS_VERIFIED.labels(status=check.status).inc()
        attached: set[str] = set()
        for match in check.matches:
            finding = by_id.get(match.finding_id)
            if finding is None:
                continue
            claim.evidence.append(_evidence(db, finding, match.derived_formula, match.value_key))
            attached.add(finding.id)
        for label in check.citations:
            finding = by_label.get(label)
            if finding is not None and finding.id not in attached and check.status != "removed":
                claim.evidence.append(_evidence(db, finding, None, None))
                attached.add(finding.id)
        db.add(claim)
        created.append(claim)
    db.flush()
    return created


def _evidence(db: Session, finding: Finding, derived_formula: str | None, value_key: str | None) -> Evidence:
    source_type = "metadata"
    if finding.result_table_id:
        table = db.get(ResultTable, finding.result_table_id)
        if table is not None:
            source_type = _SOURCE_TYPES.get(str(table.source.get("type")), "statistics")
    if derived_formula:
        source_type = "derived"
    return Evidence(
        finding_id=finding.id,
        tool_execution_id=finding.tool_execution_id,
        result_table_id=finding.result_table_id,
        source_type=source_type,
        values=finding.values,
        formula=derived_formula or finding.formula,
        description=finding.statement + (f" (matched value: {value_key})" if value_key else ""),
    )


def verify_charts(db: Session, analysis_id: str) -> tuple[int, int]:
    """Rebuild every chart from its stored source result and compare data hashes."""
    charts = db.query(Chart).filter(Chart.analysis_id == analysis_id).all()
    ok = 0
    for chart in charts:
        source = db.get(ResultTable, chart.result_table_id) if chart.result_table_id else None
        if source is None:
            chart.verified = False
            continue
        args = chart.spec.get("args") or {}
        try:
            _, rebuilt = build_chart(
                chart.chart_type,
                source.columns,
                source.rows,
                x=args["x"],
                y=list(args.get("y") or []),
                series=args.get("series"),
                title=chart.title,
            )
            chart.verified = data_hash(rebuilt) == chart.data_hash
        except Exception:
            chart.verified = False
        ok += int(chart.verified)
    db.flush()
    return ok, len(charts)


def update_conversation_state(
    conversation: Conversation, analysis: Analysis, context_update: dict[str, Any], headline: str
) -> None:
    state = dict(conversation.state or {})
    if context_update.get("filters") is not None:
        state["filters"] = context_update.get("filters") or []
    for key in ("metric", "dimension", "period"):
        if context_update.get(key):
            state[key] = context_update[key]
    history = list(state.get("history", []))[-4:]
    history.append({"analysis_id": analysis.id, "question": analysis.question[:400], "headline": headline[:400]})
    state["history"] = history
    state["last_analysis_id"] = analysis.id
    conversation.state = state


def store_memory(db: Session, analysis: Analysis, report: VerificationReport, embed: Any) -> None:
    summary = " ".join(c.text for c in report.claims if c.section == "summary" and c.status != "removed")
    content = f"Q: {analysis.question}\nA: {report.headline}\n{summary}"[:4000]
    vector = None
    try:
        vectors = embed([content])
        vector = vectors[0] if vectors else None
    except Exception:
        log.warning("memory_embedding_failed")
    db.add(
        AnalysisMemory(
            analysis_id=analysis.id,
            user_id=analysis.user_id,
            data_source_id=analysis.data_source_id,
            content=content,
            embedding=vector,
        )
    )


def tool_stats(db: Session, analysis_id: str) -> dict[str, Any]:
    executions = db.query(ToolExecution).filter(ToolExecution.analysis_id == analysis_id).all()
    total = len(executions)
    failed = [e for e in executions if e.status != "success"]
    retries = [e for e in executions if e.attempt > 1]
    recovered = [e for e in retries if e.status == "success"]
    return {
        "tool_calls": total,
        "tool_failures": len(failed),
        "retries": len(retries),
        "recovered_retries": len(recovered),
    }
