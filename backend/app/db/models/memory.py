"""Embedded summaries of completed analyses, used by retrieve_previous_analysis (pgvector)."""

from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin, id_column

_DIM = 768
try:  # settings may be unavailable at import time in tooling contexts
    _DIM = get_settings().embedding_dimensions
except Exception:  # noqa: S110
    pass


class AnalysisMemory(TimestampMixin, Base):
    __tablename__ = "analysis_memory"

    id: Mapped[str] = id_column("mem")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any | None] = mapped_column(Vector(_DIM), nullable=True)
