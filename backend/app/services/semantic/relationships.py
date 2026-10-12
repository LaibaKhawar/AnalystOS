"""Relationship (join key) discovery between tables of one data source.

Two sources of truth:
  * declared foreign keys (external databases), reported as exact;
  * inferred keys: columns with the same name in two tables, or `<table>_id` style names pointing at an `id`
    column, accepted only when the child's distinct values are (almost) all contained in a parent column whose
    values are unique. Name similarity alone is never enough.

The result is stored on DataSource.options["relationships"] and rendered into the agent's schema context so it
can write correct JOINs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import duckdb

from app.services.ingestion.naming import quote_ident

MIN_CONTAINMENT = 0.9
SKIP_NAMES = {
    "date",
    "name",
    "description",
    "status",
    "type",
    "title",
    "notes",
    "created_at",
    "updated_at",
    "value",
    "amount",
    "price",
    "quantity",
    "total",
    "email",
    "phone",
    "address",
    "city",
    "country",
    "state",
}


@dataclass
class Relationship:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    containment: float  # share of the child's distinct values found in the parent column
    source: str  # declared | inferred
    sampled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def describe(self) -> str:
        how = "declared foreign key" if self.source == "declared" else f"{self.containment:.0%} of values match"
        sample = ", from a sample" if self.sampled else ""
        return (
            f"{self.child_table}.{self.child_column} -> {self.parent_table}.{self.parent_column} "
            f"(many-to-one, {how}{sample})"
        )


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _singular(name: str) -> str:
    name = _normalise(name)
    if name.endswith("ies"):
        return name[:-3] + "y"
    return name[:-1] if name.endswith("s") else name


def candidate_pairs(columns: dict[str, list[str]]) -> list[tuple[str, str, str, str]]:
    """(child_table, child_col, parent_table, parent_col) pairs worth testing."""
    pairs: list[tuple[str, str, str, str]] = []
    tables = list(columns)
    for child in tables:
        for parent in tables:
            if child == parent:
                continue
            parent_cols = {_normalise(c): c for c in columns[parent]}
            for col in columns[child]:
                key = _normalise(col)
                if key in SKIP_NAMES or col.lower() in SKIP_NAMES:
                    continue
                if key in parent_cols and (key.endswith("id") or key.endswith("key") or key.endswith("code")):
                    pairs.append((child, col, parent, parent_cols[key]))
                elif key in {f"{_singular(parent)}id", f"{_normalise(parent)}id"} and "id" in parent_cols:
                    pairs.append((child, col, parent, parent_cols["id"]))
    return pairs


def infer_in_duckdb(
    con: duckdb.DuckDBPyConnection,
    columns: dict[str, list[str]],
    *,
    sampled: bool = False,
    local_names: dict[str, str] | None = None,
) -> list[Relationship]:
    """Test candidate pairs on tables loaded in DuckDB. local_names maps logical table -> DuckDB table name."""
    local_names = local_names or {t: t for t in columns}
    found: list[Relationship] = []
    for child, child_col, parent, parent_col in candidate_pairs(columns):
        c_tab, p_tab = quote_ident(local_names[child]), quote_ident(local_names[parent])
        c_col, p_col = quote_ident(child_col), quote_ident(parent_col)
        try:
            row = con.execute(
                f"""SELECT
                      (SELECT count(*) = count(DISTINCT {p_col}) AND count(DISTINCT {p_col}) > 0 FROM {p_tab}),
                      (SELECT count(DISTINCT {c_col}) FROM {c_tab} WHERE {c_col} IS NOT NULL),
                      (SELECT count(DISTINCT c.{c_col}) FROM {c_tab} c
                         WHERE c.{c_col} IN (SELECT {p_col} FROM {p_tab}))"""
            ).fetchone()
        except duckdb.Error:
            continue  # incompatible types
        if not row or not row[0] or not row[1]:
            continue
        containment = float(row[2]) / float(row[1])
        if containment >= MIN_CONTAINMENT:
            found.append(Relationship(child, child_col, parent, parent_col, round(containment, 4), "inferred", sampled))
    return found


def merge(declared: list[Relationship], inferred: list[Relationship]) -> list[Relationship]:
    keys = {(r.child_table.lower(), r.child_column.lower(), r.parent_table.lower()) for r in declared}
    return declared + [
        r for r in inferred if (r.child_table.lower(), r.child_column.lower(), r.parent_table.lower()) not in keys
    ]
