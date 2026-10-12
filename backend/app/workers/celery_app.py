"""Celery application. Analyses run here so long jobs never block the API server."""

from __future__ import annotations

import contextlib

from celery import Celery
from celery.signals import worker_init, worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
celery_app = Celery("analystos", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.agent_job_timeout_seconds + 60,
    task_soft_time_limit=settings.agent_job_timeout_seconds,
    result_expires=3600,
    task_serializer="json",
    accept_content=["json"],
    beat_schedule={"dispatch-schedules": {"task": "analystos.dispatch_schedules", "schedule": 60.0}},
)


@worker_init.connect
def _start_metrics_server(**_: object) -> None:
    """Expose the worker's Prometheus metrics (tool, LLM, SQL, sandbox) on :9100."""
    if settings.metrics_enabled:
        from prometheus_client import start_http_server

        with contextlib.suppress(OSError):  # another worker on this host already serves the port
            start_http_server(9100)


@worker_process_init.connect
def _init_worker(**_: object) -> None:
    configure_logging(settings.log_level, settings.log_json)
    from app.core.tracing import configure_tracing
    from app.workers.tasks import publish_sandbox_status

    configure_tracing("analystos-worker")

    publish_sandbox_status()
