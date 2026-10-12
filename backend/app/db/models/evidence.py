"""Result tables, findings, charts, claims, evidence and reports: the provenance graph.

ToolExecution -> ResultTable -> Finding (deterministic, numeric) -> Evidence -> Claim (prose sentence)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column


class ResultTable(TimestampMixin, Base):
    __tablename__ = "result_tables"

    id: Mapped[str] = id_column("res")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    columns: Mapped[list[Any]] = mapped_column(default=list)  # [{"name":..., "type":...}]
    rows: Mapped[list[Any]] = mapped_column(default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    source: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"type": "sql", "sql": ..., "filters": ...}


class Finding(TimestampMixin, Base):
    """A deterministic, machine-generated fact produced by a tool. The only allowed source of numbers."""

    __tablename__ = "findings"

    id: Mapped[str] = id_column("fnd")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    result_table_id: Mapped[str | None] = mapped_column(ForeignKey("result_tables.id", ondelete="SET NULL"))
    label: Mapped[str] = mapped_column(String(16))  # short handle shown to the LLM: F1, F2...
    kind: Mapped[str] = mapped_column(String(32))  # value|comparison|ranking|anomaly|driver|correlation|trend|stat
    statement: Mapped[str] = mapped_column(Text)
    values: Mapped[dict[str, Any]] = mapped_column(default=dict)
    formula: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Chart(TimestampMixin, Base):
    __tablename__ = "charts"

    id: Mapped[str] = id_column("cht")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    result_table_id: Mapped[str | None] = mapped_column(ForeignKey("result_tables.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    chart_type: Mapped[str] = mapped_column(String(24))
    spec: Mapped[dict[str, Any]] = mapped_column(default=dict)
    data: Mapped[list[Any]] = mapped_column(default=list)
    data_hash: Mapped[str] = mapped_column(String(64))
    interpretation: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False)


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"

    id: Mapped[str] = id_column("clm")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(32))  # summary|finding|trend|anomaly|segment|driver|caveat
    kind: Mapped[str] = mapped_column(String(20))  # fact | interpretation | recommendation
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # verified | qualified | removed | no_numbers
    numbers: Mapped[list[Any]] = mapped_column(default=list)
    verification: Mapped[dict[str, Any]] = mapped_column(default=dict)

    evidence: Mapped[list[Evidence]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    id: Mapped[str] = id_column("evd")
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"))
    tool_execution_id: Mapped[str | None] = mapped_column(ForeignKey("tool_executions.id", ondelete="SET NULL"))
    result_table_id: Mapped[str | None] = mapped_column(ForeignKey("result_tables.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(24))  # sql_query | python | statistics | derived
    values: Mapped[dict[str, Any]] = mapped_column(default=dict)
    formula: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    claim: Mapped[Claim] = relationship(back_populates="evidence")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[str] = id_column("rpt")
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    html: Mapped[str] = mapped_column(Text)
