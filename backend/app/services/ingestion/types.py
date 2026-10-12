"""Shared ingestion result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoadedTable:
    name: str
    display_name: str
    original_columns: list[str]
    columns: list[str]
    row_count: int
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    tables: list[LoadedTable]
    file_type: str
    report: dict[str, Any] = field(default_factory=dict)
