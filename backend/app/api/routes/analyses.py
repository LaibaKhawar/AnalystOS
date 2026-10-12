from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import current_user, owned_analysis
from app.api.schemas import AnalysisOut, ChartOut, ClaimOut, EventOut, ExecutionOut
from app.core.errors import NotFoundError, ValidationFailed
from app.db.models import (
    Analysis,
    AnalysisEvent,
    Chart,
    Claim,
    Evidence,
    Finding,
    Message,
    PythonExecution,
    ResultTable,
    SQLExecution,
    ToolExecution,
    User,
)
from app.db.session import get_db, get_session_factory
from app.services.reports.builder import result_csv
from app.workers.dispatch import enqueue_analysis

router = APIRouter(prefix="/api/analyses", tags=["analyses"])
TERMINAL = {"completed", "failed", "cancelled", "needs_clarification"}


def reap_stale(db: Session, analysis: Analysis) -> Analysis:
    """A job that no worker picked up (or whose worker died) must not stay 'queued'/'running' forever."""
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings

    limit = timedelta(seconds=get_settings().agent_job_timeout_seconds + 120)
    reference = analysis.started_at or analysis.created_at
    if analysis.status in {"queued", "running"} and reference and datetime.now(UTC) - reference > limit:
        analysis.status = "failed"
        analysis.error = (
            "The analysis did not finish: no worker picked it up or the worker stopped. "
            "Check that the worker is running, then retry."
        )
        db.commit()
    return analysis


@router.get("", response_model=list[AnalysisOut])
def recent(limit: int = 20, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Analysis]:
    rows = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [reap_stale(db, a) for a in rows]


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Analysis:
    return reap_stale(db, owned_analysis(db, user, analysis_id))


@router.post("/{analysis_id}/cancel", response_model=AnalysisOut)
def cancel(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Analysis:
    analysis = owned_analysis(db, user, analysis_id)
    if analysis.status in TERMINAL:
        raise ValidationFailed("This analysis has already finished")
    analysis.cancel_requested = True
    if analysis.status == "queued":
        analysis.status = "cancelled"
    db.commit()
    return analysis


@router.post("/{analysis_id}/retry", response_model=AnalysisOut, status_code=202)
def retry(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Analysis:
    original = owned_analysis(db, user, analysis_id)
    if original.status not in {"failed", "cancelled"}:
        raise ValidationFailed("Only failed or cancelled analyses can be retried")
    analysis = Analysis(
        conversation_id=original.conversation_id,
        user_id=user.id,
        data_source_id=original.data_source_id,
        question=original.question,
        status="queued",
    )
    db.add(analysis)
    db.flush()
    db.add(
        Message(
            conversation_id=original.conversation_id, role="user", content=original.question, analysis_id=analysis.id
        )
    )
    db.commit()
    enqueue_analysis(analysis.id)
    return analysis


@router.get("/{analysis_id}/events", response_model=list[EventOut])
def events(
    analysis_id: str, after: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[AnalysisEvent]:
    owned_analysis(db, user, analysis_id)
    return (
        db.query(AnalysisEvent)
        .filter(AnalysisEvent.analysis_id == analysis_id, AnalysisEvent.id > after)
        .order_by(AnalysisEvent.id)
        .limit(500)
        .all()
    )


@router.get("/{analysis_id}/stream")
async def stream(
    analysis_id: str,
    request: Request,
    after: int = 0,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    owned_analysis(db, user, analysis_id)

    async def generator() -> AsyncIterator[dict[str, str]]:
        last = after
        idle_terminal = 0
        while not await request.is_disconnected():
            session = get_session_factory()()
            try:
                rows = (
                    session.query(AnalysisEvent)
                    .filter(AnalysisEvent.analysis_id == analysis_id, AnalysisEvent.id > last)
                    .order_by(AnalysisEvent.id)
                    .limit(200)
                    .all()
                )
                status = session.query(Analysis.status).filter(Analysis.id == analysis_id).scalar()
            finally:
                session.close()
            for row in rows:
                last = row.id
                yield {
                    "id": str(row.id),
                    "event": "progress",
                    "data": json.dumps(
                        {
                            "id": row.id,
                            "type": row.type,
                            "message": row.message,
                            "payload": row.payload,
                            "created_at": row.created_at.isoformat(),
                        },
                        default=str,
                    ),
                }
            if status in TERMINAL and not rows:
                idle_terminal += 1
                if idle_terminal >= 2:
                    yield {"event": "end", "data": json.dumps({"status": status})}
                    return
            await asyncio.sleep(0.5)

    return EventSourceResponse(generator(), ping=15)


@router.get("/{analysis_id}/executions", response_model=list[ExecutionOut])
def executions(
    analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[ToolExecution]:
    owned_analysis(db, user, analysis_id)
    return (
        db.query(ToolExecution)
        .filter(ToolExecution.analysis_id == analysis_id)
        .order_by(ToolExecution.created_at)
        .all()
    )


@router.get("/{analysis_id}/executions/{execution_id}")
def execution_detail(
    analysis_id: str, execution_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    owned_analysis(db, user, analysis_id)
    execution = db.get(ToolExecution, execution_id)
    if execution is None or execution.analysis_id != analysis_id:
        raise NotFoundError("Execution not found")
    sql = (
        db.query(SQLExecution)
        .filter(SQLExecution.tool_execution_id == execution_id)
        .order_by(SQLExecution.created_at)
        .all()
    )
    python = db.query(PythonExecution).filter(PythonExecution.tool_execution_id == execution_id).all()
    results = db.query(ResultTable).filter(ResultTable.tool_execution_id == execution_id).all()
    return {
        "execution": ExecutionOut.model_validate(execution).model_dump(mode="json"),
        "sql": [
            {
                "id": s.id,
                "dialect": s.dialect,
                "sql_original": s.sql_original,
                "sql_executed": s.sql_executed,
                "status": s.status,
                "row_count": s.row_count,
                "truncated": s.truncated,
                "error": s.error,
                "duration_ms": s.duration_ms,
                "validation": s.validation,
                "created_at": s.created_at.isoformat(),
            }
            for s in sql
        ],
        "python": [
            {
                "id": p.id,
                "code": p.code,
                "status": p.status,
                "stdout": p.stdout,
                "stderr": p.stderr,
                "static_check": p.static_check,
                "limits": p.limits,
                "duration_ms": p.duration_ms,
                "exit_code": p.exit_code,
                "artifacts": [{"file": a["file"], "title": a.get("title")} for a in p.artifacts],
            }
            for p in python
        ],
        "results": [
            {
                "id": r.id,
                "name": r.name,
                "columns": r.columns,
                "rows": r.rows[:200],
                "row_count": r.row_count,
                "truncated": r.truncated,
                "source": r.source,
            }
            for r in results
        ],
    }


@router.get("/{analysis_id}/artifacts/{python_id}/{file_name}")
def artifact(
    analysis_id: str, python_id: str, file_name: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> FileResponse:
    owned_analysis(db, user, analysis_id)
    record = db.get(PythonExecution, python_id)
    if record is None or record.analysis_id != analysis_id:
        raise NotFoundError("Artifact not found")
    match = next((a for a in record.artifacts if a["file"] == file_name), None)
    if match is None:
        raise NotFoundError("Artifact not found")
    return FileResponse(match["path"], media_type="image/png")


@router.get("/{analysis_id}/charts", response_model=list[ChartOut])
def charts(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Chart]:
    owned_analysis(db, user, analysis_id)
    return db.query(Chart).filter(Chart.analysis_id == analysis_id).order_by(Chart.created_at).all()


@router.get("/{analysis_id}/claims", response_model=list[ClaimOut])
def claims(
    analysis_id: str, include_removed: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[Claim]:
    owned_analysis(db, user, analysis_id)
    query = db.query(Claim).filter(Claim.analysis_id == analysis_id)
    if not include_removed:
        query = query.filter(Claim.status != "removed")
    return query.order_by(Claim.ordinal).all()


@router.get("/{analysis_id}/findings")
def findings(
    analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    owned_analysis(db, user, analysis_id)
    rows = db.query(Finding).filter(Finding.analysis_id == analysis_id).order_by(Finding.created_at).all()
    return [
        {
            "id": f.id,
            "label": f.label,
            "kind": f.kind,
            "statement": f.statement,
            "values": f.values,
            "formula": f.formula,
            "tool_execution_id": f.tool_execution_id,
            "result_table_id": f.result_table_id,
        }
        for f in rows
    ]


@router.get("/{analysis_id}/claims/{claim_id}/evidence")
def claim_evidence(
    analysis_id: str, claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    """Everything needed to audit one claim: findings, formulas, SQL/Python, result rows, timestamps."""
    owned_analysis(db, user, analysis_id)
    claim = db.get(Claim, claim_id)
    if claim is None or claim.analysis_id != analysis_id:
        raise NotFoundError("Claim not found")
    items = []
    for evidence in db.query(Evidence).filter(Evidence.claim_id == claim.id).all():
        finding = db.get(Finding, evidence.finding_id) if evidence.finding_id else None
        execution = db.get(ToolExecution, evidence.tool_execution_id) if evidence.tool_execution_id else None
        table = db.get(ResultTable, evidence.result_table_id) if evidence.result_table_id else None
        sql = (
            db.query(SQLExecution)
            .filter(SQLExecution.tool_execution_id == evidence.tool_execution_id)
            .order_by(SQLExecution.created_at)
            .all()
            if evidence.tool_execution_id
            else []
        )
        python = (
            db.query(PythonExecution).filter(PythonExecution.tool_execution_id == evidence.tool_execution_id).all()
            if evidence.tool_execution_id
            else []
        )
        items.append(
            {
                "id": evidence.id,
                "source_type": evidence.source_type,
                "values": evidence.values,
                "formula": evidence.formula,
                "description": evidence.description,
                "finding": {"label": finding.label, "statement": finding.statement, "kind": finding.kind}
                if finding
                else None,
                "execution": {
                    "id": execution.id,
                    "tool": execution.tool,
                    "status": execution.status,
                    "attempt": execution.attempt,
                    "input": execution.input,
                    "duration_ms": execution.duration_ms,
                    "created_at": execution.created_at.isoformat(),
                }
                if execution
                else None,
                "sql": [
                    {
                        "id": s.id,
                        "sql": s.sql_executed or s.sql_original,
                        "status": s.status,
                        "row_count": s.row_count,
                        "duration_ms": s.duration_ms,
                        "created_at": s.created_at.isoformat(),
                    }
                    for s in sql
                ],
                "python": [
                    {"id": p.id, "code": p.code, "status": p.status, "duration_ms": p.duration_ms} for p in python
                ],
                "result": {
                    "id": table.id,
                    "name": table.name,
                    "columns": table.columns,
                    "rows": table.rows[:100],
                    "row_count": table.row_count,
                    "truncated": table.truncated,
                }
                if table
                else None,
            }
        )
    return {"claim": ClaimOut.model_validate(claim).model_dump(mode="json"), "evidence": items}


@router.get("/{analysis_id}/results/{result_id}.csv", response_class=PlainTextResponse)
def result_download(
    analysis_id: str, result_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> PlainTextResponse:
    owned_analysis(db, user, analysis_id)
    table = db.get(ResultTable, result_id)
    if table is None or table.analysis_id != analysis_id:
        raise NotFoundError("Result not found")
    return PlainTextResponse(
        result_csv(table),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result_id}.csv"'},
    )
