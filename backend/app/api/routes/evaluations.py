from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFoundError
from app.db.models import EvaluationCase, EvaluationRun, User
from app.db.session import get_db

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _run(run: EvaluationRun) -> dict[str, object]:
    return {
        "id": run.id,
        "suite": run.suite,
        "model": run.model,
        "status": run.status,
        "metrics": run.metrics,
        "config": run.config,
        "notes": run.notes,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("")
def runs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """System benchmark runs (no owner) are visible to everyone; other runs only to their owner."""
    query = db.query(EvaluationRun).filter(or_(EvaluationRun.user_id.is_(None), EvaluationRun.user_id == user.id))
    return [_run(r) for r in query.order_by(EvaluationRun.created_at.desc()).limit(50).all()]


@router.get("/{run_id}")
def run_detail(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    run = db.get(EvaluationRun, run_id)
    if run is None or (run.user_id is not None and run.user_id != user.id):
        raise NotFoundError("Evaluation run not found")
    cases = db.query(EvaluationCase).filter(EvaluationCase.run_id == run.id).order_by(EvaluationCase.created_at).all()
    return {
        **_run(run),
        "cases": [
            {
                "id": c.id,
                "case_id": c.case_id,
                "category": c.category,
                "dataset": c.dataset,
                "question": c.question,
                "expected": c.expected,
                "answer": c.answer,
                "passed": c.passed,
                "scores": c.scores,
                "latency_ms": c.latency_ms,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "cost_usd": c.cost_usd,
                "error": c.error,
                "analysis_id": c.analysis_id,
            }
            for c in cases
        ],
    }
