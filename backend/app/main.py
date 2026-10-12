"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import admin, analyses, auth, conversations, evaluations, reports, sources, system
from app.api.routes import metrics as metric_routes
from app.core.config import get_settings
from app.core.errors import AnalystError
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.tracing import configure_tracing

log = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    configure_tracing("analystos-api")
    app = FastAPI(
        title="AnalystOS API",
        version="1.0.0",
        description="Autonomous, evidence-backed data analyst. Every number is traceable to its query.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request_id_var.set(request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not request.url.path.endswith(("/stream", "/metrics")):
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        return response

    @app.exception_handler(AnalystError)
    async def analyst_error(_: Request, exc: AnalystError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        problems = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()[:5]]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_failed", "message": "; ".join(problems), "details": {}}},
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=exc.__class__.__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side",
                    "details": {"request_id": request_id_var.get()},
                }
            },
        )

    for router in (
        auth.router,
        sources.router,
        conversations.router,
        analyses.router,
        reports.router,
        evaluations.router,
        admin.router,
        metric_routes.router,
        system.router,
    ):
        app.include_router(router)

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
