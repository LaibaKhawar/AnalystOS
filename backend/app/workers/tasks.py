"""Background tasks."""

from __future__ import annotations

from celery.exceptions import SoftTimeLimitExceeded

from app.agent.llm.openai_compat import get_provider
from app.agent.orchestrator import AnalysisRunner
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import Analysis, Schedule
from app.db.session import get_session_factory
from app.workers.celery_app import celery_app

log = get_logger(__name__)


SANDBOX_STATUS_KEY = "analystos:sandbox_status"


def publish_sandbox_status() -> None:
    """The worker, not the API, starts sandboxes: report its view of sandbox availability for /api/system/status."""
    try:
        import json

        import redis

        from app.core.config import get_settings
        from app.services.sandbox.factory import get_sandbox

        ok, detail = get_sandbox().available()
        redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).set(
            SANDBOX_STATUS_KEY, json.dumps({"ok": ok, "detail": detail}), ex=900
        )
    except Exception:
        log.warning("sandbox_status_publish_failed")


def execute_analysis(analysis_id: str) -> str:
    publish_sandbox_status()
    session = get_session_factory()()
    try:
        analysis = AnalysisRunner(session, get_provider()).run(analysis_id)
        return analysis.status
    finally:
        session.close()


@celery_app.task(name="analystos.dispatch_schedules")
def dispatch_schedules() -> int:
    """Beat task (every minute): start due scheduled analyses."""
    session = get_session_factory()()
    try:
        from app.services.schedules import dispatch_due

        pairs = []
        for analysis_id in dispatch_due(session):
            schedule_id = session.query(Schedule.id).filter(Schedule.last_analysis_id == analysis_id).scalar()
            pairs.append((analysis_id, schedule_id))
    finally:
        session.close()
    for analysis_id, schedule_id in pairs:
        run_scheduled_analysis.delay(analysis_id, schedule_id)
    return len(pairs)


@celery_app.task(name="analystos.run_scheduled_analysis", max_retries=0)
def run_scheduled_analysis(analysis_id: str, schedule_id: str) -> str:
    status = execute_analysis(analysis_id)
    raise_alerts(analysis_id, schedule_id)
    return status


def raise_alerts(analysis_id: str, schedule_id: str) -> None:
    from app.services.schedules import create_alerts

    session = get_session_factory()()
    try:
        schedule = session.get(Schedule, schedule_id)
        analysis = session.get(Analysis, analysis_id)
        if schedule is not None and analysis is not None:
            create_alerts(session, schedule, analysis)
    finally:
        session.close()


@celery_app.task(name="analystos.run_analysis", bind=True, max_retries=0)
def run_analysis(self: object, analysis_id: str) -> str:
    try:
        return execute_analysis(analysis_id)
    except SoftTimeLimitExceeded:
        _mark_failed(analysis_id, "The analysis exceeded the job time limit")
        return "failed"
    except Exception:
        log.exception("analysis_task_crashed", analysis=analysis_id)
        _mark_failed(analysis_id, "The analysis failed unexpectedly")
        return "failed"


def _mark_failed(analysis_id: str, message: str) -> None:
    """Last-resort guard: never leave an analysis in queued/running after the task ends."""
    session = get_session_factory()()
    try:
        analysis = session.get(Analysis, analysis_id)
        if analysis is not None and analysis.status in {"queued", "running"}:
            analysis.status, analysis.error = "failed", message
            analysis.completed_at = utcnow()
            session.commit()
    finally:
        session.close()
