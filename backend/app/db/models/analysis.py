"""Conversations, analyses, plan steps, streaming events, and tool executions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column, utcnow


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = id_column("cnv")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    # Structured analytical context carried across turns (filters, metric, dimension, time range...)
    state: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = id_column("msg")
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Analysis(TimestampMixin, Base):
    __tablename__ = "analyses"

    id: Mapped[str] = id_column("ana")
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    # queued | running | completed | failed | needs_clarification | cancelled
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    plan: Mapped[dict[str, Any]] = mapped_column(default=dict)
    answer: Mapped[dict[str, Any]] = mapped_column(default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    replans: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list[AnalysisStep]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="AnalysisStep.ordinal"
    )


class AnalysisStep(TimestampMixin, Base):
    __tablename__ = "analysis_steps"

    id: Mapped[str] = id_column("stp")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    tool: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str | None] = mapped_column(Text)
    depends_on: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed|skipped
    added_by_replan: Mapped[bool] = mapped_column(default=False)
    result_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analysis: Mapped[Analysis] = relationship(back_populates="steps")


class AnalysisEvent(Base):
    """Append-only progress feed streamed to the UI over SSE. Never contains model reasoning."""

    __tablename__ = "analysis_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolExecution(TimestampMixin, Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = id_column("exec")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_steps.id", ondelete="SET NULL"))
    tool: Mapped[str] = mapped_column(String(64), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16))  # success | error
    error: Mapped[str | None] = mapped_column(Text)
    error_kind: Mapped[str | None] = mapped_column(String(48))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    retry_of_id: Mapped[str | None] = mapped_column(String(40))
    retry_reason: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class SQLExecution(TimestampMixin, Base):
    __tablename__ = "sql_executions"

    id: Mapped[str] = id_column("sql")
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    dialect: Mapped[str] = mapped_column(String(24))
    sql_original: Mapped[str] = mapped_column(Text)
    sql_executed: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16))  # success | blocked | error | timeout
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class PythonExecution(TimestampMixin, Base):
    __tablename__ = "python_executions"

    id: Mapped[str] = id_column("py")
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(Text)
    static_check: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16))  # success | blocked | error | timeout
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    artifacts: Mapped[list[Any]] = mapped_column(default=list)
    limits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
