from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column


class EvaluationRun(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = id_column("evr")
    # NULL = system benchmark run (CLI), visible to everyone; otherwise visible to its owner only.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    suite: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="running")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cases: Mapped[list[EvaluationCase]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EvaluationCase.created_at"
    )


class EvaluationCase(TimestampMixin, Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[str] = id_column("evc")
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(48))
    dataset: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    expected: Mapped[dict[str, Any]] = mapped_column(default=dict)
    answer: Mapped[str | None] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(default=False)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    analysis_id: Mapped[str | None] = mapped_column(String(40))

    run: Mapped[EvaluationRun] = relationship(back_populates="cases")
