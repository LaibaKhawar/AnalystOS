"""Request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    user: UserOut


class UserOut(ORM):
    id: str
    email: str
    name: str
    is_admin: bool


class ColumnOut(ORM):
    id: str
    name: str
    original_name: str
    ordinal: int
    physical_type: str
    inferred_type: str
    role: str
    semantic_type: str | None
    semantic_confidence: float
    semantic_source: str
    is_pii: bool
    stats: dict[str, Any]


class TableOut(ORM):
    id: str
    name: str
    display_name: str
    row_count: int
    column_count: int
    profile: dict[str, Any]
    semantic: dict[str, Any]
    columns: list[ColumnOut] = []


class SourceOut(ORM):
    id: str
    kind: str
    name: str
    status: str
    error: str | None
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    db_schema: str | None
    allowed_tables: list[Any] | None
    restricted_columns: list[Any]
    created_at: datetime
    last_checked_at: datetime | None
    has_password: bool = False
    table_count: int = 0
    row_count: int = 0
    dataset_id: str | None = None
    file_type: str | None = None
    size_bytes: int | None = None
    ingestion_report: dict[str, Any] | None = None


class ConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["postgresql", "mysql", "sqlite"]
    host: str | None = Field(None, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str | None = Field(None, max_length=255)
    password: str | None = Field(None, max_length=500)
    db_schema: str | None = Field(None, max_length=255)
    allowed_tables: list[str] | None = None
    restricted_columns: list[str] = Field(default_factory=list, description="'table.column' entries hidden as PII")


class ColumnPatch(BaseModel):
    semantic_type: str | None = None
    role: Literal["metric", "dimension", "identifier", "time", "text", "other"] | None = None
    is_pii: bool | None = None


class ConversationIn(BaseModel):
    data_source_id: str
    title: str | None = None


class ConversationOut(ORM):
    id: str
    data_source_id: str
    title: str
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MessageOut(ORM):
    id: str
    role: str
    content: str
    analysis_id: str | None
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=4000)


class StepOut(ORM):
    id: str
    ordinal: int
    title: str
    tool: str
    purpose: str | None
    depends_on: list[Any]
    status: str
    added_by_replan: bool
    result_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None


class AnalysisOut(ORM):
    id: str
    conversation_id: str
    data_source_id: str
    question: str
    status: str
    plan: dict[str, Any]
    answer: dict[str, Any]
    summary: str | None
    error: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    llm_calls: int
    cost_usd: float
    latency_ms: int | None
    replans: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[StepOut] = []


class EventOut(ORM):
    id: int
    type: str
    message: str
    payload: dict[str, Any]
    created_at: datetime


class ChartOut(ORM):
    id: str
    title: str
    chart_type: str
    spec: dict[str, Any]
    data: list[Any]
    data_hash: str
    interpretation: str | None
    verified: bool
    result_table_id: str | None


class EvidenceOut(ORM):
    id: str
    finding_id: str | None
    tool_execution_id: str | None
    result_table_id: str | None
    source_type: str
    values: dict[str, Any]
    formula: str | None
    description: str | None


class ClaimOut(ORM):
    id: str
    ordinal: int
    section: str
    kind: str
    text: str
    original_text: str | None
    status: str
    numbers: list[Any]
    verification: dict[str, Any]
    evidence: list[EvidenceOut] = []


class ExecutionOut(ORM):
    id: str
    step_id: str | None
    tool: str
    input: dict[str, Any]
    output: dict[str, Any]
    status: str
    error: str | None
    error_kind: str | None
    attempt: int
    retry_of_id: str | None
    retry_reason: str | None
    duration_ms: int
    created_at: datetime


class ReportOut(ORM):
    id: str
    analysis_id: str
    title: str
    content: dict[str, Any]
    created_at: datetime


TokenOut.model_rebuild()
