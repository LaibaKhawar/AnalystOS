"""Query engine abstraction shared by uploaded datasets (DuckDB) and external SQL databases."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    columns: list[dict[str, str]]
    rows: list[list[Any]]
    truncated: bool
    duration_ms: int
    executed_sql: str = ""

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def records(self) -> list[dict[str, Any]]:
        names = [c["name"] for c in self.columns]
        return [dict(zip(names, row, strict=False)) for row in self.rows]


@dataclass
class ColumnInfo:
    name: str
    type: str


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    row_count: int | None = None


class QueryTimeout(Exception):
    pass


class QueryFailed(Exception):
    pass


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    if hasattr(value, "item"):  # numpy scalar
        return to_jsonable(value.item())
    return str(value)


class QueryEngine(ABC):
    """Executes already-validated, read-only SQL. Validation happens in app.services.sql.validator."""

    dialect: str

    @abstractmethod
    def list_tables(self) -> list[TableInfo]: ...

    @abstractmethod
    def execute(self, sql: str, *, max_rows: int, timeout_seconds: float) -> QueryResult: ...

    @abstractmethod
    def export_table_parquet(self, table: str, target: str, *, max_rows: int) -> int:
        """Write (up to max_rows of) a table to a parquet file for the Python sandbox."""

    def close(self) -> None:  # noqa: B027 - optional hook
        pass
