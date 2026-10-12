"""Domain errors. API handlers map these to HTTP responses with safe, user-facing messages."""

from __future__ import annotations


class AnalystError(Exception):
    """Base error. `message` is always safe to show to end users."""

    status_code = 400
    code = "error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AnalystError):
    status_code = 404
    code = "not_found"


class ValidationFailed(AnalystError):
    status_code = 422
    code = "validation_failed"


class IngestionError(AnalystError):
    status_code = 422
    code = "ingestion_failed"


class UnsafeSQLError(AnalystError):
    status_code = 400
    code = "unsafe_sql"


class ConnectionFailed(AnalystError):
    status_code = 400
    code = "connection_failed"


class ForbiddenError(AnalystError):
    status_code = 403
    code = "forbidden"


class AuthError(AnalystError):
    status_code = 401
    code = "unauthorized"


class LLMError(AnalystError):
    status_code = 502
    code = "llm_error"
