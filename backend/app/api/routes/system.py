from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.db.models import Analysis, DataSource, Report, User
from app.db.session import get_db
from app.services.sandbox.docker_runner import DockerSandbox

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "down"
    try:
        import redis

        redis.Redis.from_url(get_settings().redis_url, socket_timeout=1).ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
    return {"status": "ok" if checks["database"] == "ok" else "degraded", "checks": checks}


@router.get("/api/system/status")
def status(_: User = Depends(current_user)) -> dict[str, object]:
    settings = get_settings()
    llm = "unknown"
    try:
        response = httpx.get(settings.llm_base_url.rstrip("/") + "/models",
                             headers={"Authorization": f"Bearer {settings.llm_api_key}"}, timeout=3)
        llm = "ok" if response.status_code < 400 else f"http {response.status_code}"
    except Exception:
        llm = "unreachable"
    sandbox_ok, sandbox_reason = DockerSandbox().available()
    return {
        "llm": {"status": llm, "provider": settings.llm_provider, "model": settings.llm_model},
        "sandbox": {"status": "ok" if sandbox_ok else "unavailable", "detail": sandbox_reason,
                    "limits": {"cpus": settings.sandbox_cpus, "memory_mb": settings.sandbox_memory_mb,
                               "timeout_seconds": settings.sandbox_timeout_seconds, "network": "none"}},
        "sql": {"max_rows": settings.sql_max_rows, "timeout_seconds": settings.sql_timeout_seconds},
        "worker_mode": "inline" if settings.run_analyses_inline else "celery",
    }


@router.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    sources = db.query(DataSource).filter(DataSource.user_id == user.id).all()
    stats = db.query(func.count(Analysis.id), func.coalesce(func.sum(Analysis.cost_usd), 0.0),
                     func.coalesce(func.sum(Analysis.input_tokens + Analysis.output_tokens), 0),
                     func.avg(Analysis.latency_ms)).filter(Analysis.user_id == user.id).one()
    by_status = dict(db.query(Analysis.status, func.count(Analysis.id)).filter(Analysis.user_id == user.id)
                     .group_by(Analysis.status).all())
    return {
        "datasets": sum(1 for s in sources if s.kind == "file"),
        "connections": sum(1 for s in sources if s.kind != "file"),
        "connections_ready": sum(1 for s in sources if s.kind != "file" and s.status == "ready"),
        "analyses": int(stats[0]), "total_cost_usd": float(stats[1]), "total_tokens": int(stats[2]),
        "avg_latency_ms": float(stats[3]) if stats[3] is not None else None, "analyses_by_status": by_status,
        "reports": db.query(Report).filter(Report.user_id == user.id).count(),
    }
