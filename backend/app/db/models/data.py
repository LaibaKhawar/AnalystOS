"""Data sources, uploaded datasets, versions, and table/column metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column


class DataSource(TimestampMixin, Base):
    """Anything the agent can query: an uploaded file dataset or an external SQL database."""

    __tablename__ = "data_sources"

    id: Mapped[str] = id_column("src")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # file | postgresql | mysql | sqlite
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ready|failed
    error: Mapped[str | None] = mapped_column(Text)
    # Connection settings (external databases only). The password is stored encrypted.
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    db_schema: Mapped[str | None] = mapped_column(String(255))
    options: Mapped[dict[str, Any]] = mapped_column(default=dict)
    allowed_tables: Mapped[list[Any] | None] = mapped_column(default=None)
    restricted_columns: Mapped[list[Any]] = mapped_column(default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset | None] = relationship(back_populates="data_source", uselist=False)
    tables: Mapped[list[TableMetadata]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan", order_by="TableMetadata.name"
    )


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"

    id: Mapped[str] = id_column("ds")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(400))
    file_type: Mapped[str] = mapped_column(String(10))  # csv | xlsx
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    current_version_id: Mapped[str | None] = mapped_column(String(40))

    data_source: Mapped[DataSource] = relationship(back_populates="dataset")
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version"
    )


class DatasetVersion(TimestampMixin, Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = id_column("dsv")
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)  # DuckDB database file
    parquet_dir: Mapped[str] = mapped_column(Text)  # per-table parquet for the sandbox
    sha256: Mapped[str] = mapped_column(String(64))
    ingestion_report: Mapped[dict[str, Any]] = mapped_column(default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")


class TableMetadata(TimestampMixin, Base):
    __tablename__ = "table_metadata"

    id: Mapped[str] = id_column("tbl")
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))  # SQL-safe identifier
    display_name: Mapped[str] = mapped_column(String(255))  # sheet / original table name
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    semantic: Mapped[dict[str, Any]] = mapped_column(default=dict)

    data_source: Mapped[DataSource] = relationship(back_populates="tables")
    columns: Mapped[list[ColumnMetadata]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="ColumnMetadata.ordinal"
    )


class ColumnMetadata(Base):
    __tablename__ = "column_metadata"

    id: Mapped[str] = id_column("col")
    table_id: Mapped[str] = mapped_column(ForeignKey("table_metadata.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    ordinal: Mapped[int] = mapped_column(Integer)
    physical_type: Mapped[str] = mapped_column(String(64))
    inferred_type: Mapped[str] = mapped_column(String(32))  # integer|float|string|date|datetime|boolean
    role: Mapped[str] = mapped_column(String(32))  # metric|dimension|identifier|time|text|other
    semantic_type: Mapped[str | None] = mapped_column(String(64))
    semantic_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    semantic_source: Mapped[str] = mapped_column(String(16), default="rules")  # rules|user
    is_pii: Mapped[bool] = mapped_column(default=False)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)

    table: Mapped[TableMetadata] = relationship(back_populates="columns")
