"""Enqueue analyses on Celery, or run them in a thread when RUN_ANALYSES_INLINE=true (tests / no Redis)."""

from __future__ import annotations

import threading

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def enqueue_analysis(analysis_id: str) -> None:
    if get_settings().run_analyses_inline:
        from app.workers.tasks import execute_analysis

        threading.Thread(target=execute_analysis, args=(analysis_id,), daemon=True).start()
        return
    from app.workers.tasks import run_analysis

    run_analysis.delay(analysis_id)
    log.info("analysis_enqueued", analysis=analysis_id)
