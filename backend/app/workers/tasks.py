"""Background tasks."""

from __future__ import annotations

from celery.exceptions import SoftTimeLimitExceeded

from app.agent.llm.openai_compat import get_provider
from app.agent.orchestrator import AnalysisRunner
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import Analysis
from app.db.session import get_session_factory
from app.workers.celery_app import celery_app

log = get_logger(__name__)


def execute_analysis(analysis_id: str) -> str:
    session = get_session_factory()()
    try:
        analysis = AnalysisRunner(session, get_provider()).run(analysis_id)
        return analysis.status
    finally:
        session.close()


@celery_app.task(name="analystos.run_analysis", bind=True, max_retries=0)
def run_analysis(self: object, analysis_id: str) -> str:
    try:
        return execute_analysis(analysis_id)
    except SoftTimeLimitExceeded:
        session = get_session_factory()()
        try:
            analysis = session.get(Analysis, analysis_id)
            if analysis is not None:
                analysis.status, analysis.error = "failed", "The analysis exceeded the job time limit"
                analysis.completed_at = utcnow()
                session.commit()
        finally:
            session.close()
        return "failed"
