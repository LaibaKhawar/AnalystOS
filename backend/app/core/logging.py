"""Structured logging with request/analysis context propagated through contextvars."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
analysis_id_var: ContextVar[str | None] = ContextVar("analysis_id", default=None)
dataset_id_var: ContextVar[str | None] = ContextVar("dataset_id", default=None)

_SECRET_KEYS = ("password", "secret", "api_key", "token", "authorization", "encryption_key")


def _add_context(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for name, var in (
        ("request_id", request_id_var),
        ("user_id", user_id_var),
        ("analysis_id", analysis_id_var),
        ("dataset_id", dataset_id_var),
    ):
        value = var.get()
        if value is not None and name not in event_dict:
            event_dict[name] = value
    return event_dict


def _redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if any(marker in key.lower() for marker in _SECRET_KEYS):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    for noisy in ("fontTools", "weasyprint", "matplotlib", "httpx", "httpcore", "docker", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    renderer: Any = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_context,
            _redact,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
