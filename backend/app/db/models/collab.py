"""Sharing, saved metric definitions, schedules and alerts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, id_column


class SourceShare(TimestampMixin, Base):
    """Grants another user access to a data source. viewer: browse; analyst: browse and ask questions."""

    __tablename__ = "source_shares"
    __table_args__ = (UniqueConstraint("data_source_id", "user_id"),)

    id: Mapped[str] = id_column("shr")
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class MetricDefinition(TimestampMixin, Base):
    """A named business metric ("average order value = SUM(revenue) / COUNT(*)") the agent must reuse."""

    __tablename__ = "metric_definitions"
    __table_args__ = (UniqueConstraint("data_source_id", "name"),)

    id: Mapped[str] = id_column("met")
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    table_name: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    expression: Mapped[str] = mapped_column(Text)  # validated aggregate SQL expression over table columns
    filters: Mapped[list[Any]] = mapped_column(default=list)
    format: Mapped[str] = mapped_column(String(16), default="number")  # number | currency | percent
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class Schedule(TimestampMixin, Base):
    """Re-runs a question on a cadence and raises alerts when the analysis finds anomalies."""

    __tablename__ = "schedules"

    id: Mapped[str] = id_column("sch")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    interval_minutes: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(default=True)
    alert_min_severity: Mapped[str] = mapped_column(String(16), default="medium")  # low | medium | high
    webhook_url: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_analysis_id: Mapped[str | None] = mapped_column(String(40))


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"

    id: Mapped[str] = id_column("alr")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[str | None] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    delivery_status: Mapped[str] = mapped_column(String(32), default="not_configured")  # sent | failed | ...
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
