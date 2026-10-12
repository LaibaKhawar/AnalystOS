"""Convert text columns that really hold numbers ("$1,234.50", "12%", "(300)") or dates into typed columns.

Runs inside DuckDB so it scales to large tables. A conversion is applied only when nearly every
non-null value parses, so free-text columns are never silently mangled.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from app.services.ingestion.naming import quote_ident, sql_string

PARSE_THRESHOLD = 0.97
_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%b %d, %Y", "%d %b %Y",
                 "%B %d, %Y", "%Y-%m"]
_DATETIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"]


@dataclass
class Coercion:
    column: str
    to_type: str
    unit: str | None = None
    date_format: str | None = None
    ambiguous: bool = False


def _numeric_expr(col: str) -> str:
    cleaned = (
        f"regexp_replace(regexp_replace(trim({col}), '^\\((.*)\\)$', '-\\1'), "
        f"'[\\$€£¥,%\\s]|USD|EUR|GBP|PKR|Rs\\.?', '', 'g')"
    )
    return f"TRY_CAST({cleaned} AS DOUBLE)"


def _rate(con: duckdb.DuckDBPyConnection, table: str, expr: str, col: str) -> tuple[float, int]:
    row = con.execute(
        f"SELECT count({col}), count({expr}) FROM {quote_ident(table)} WHERE trim({col}) <> ''"
    ).fetchone()
    total, parsed = (int(row[0]), int(row[1])) if row else (0, 0)
    return (parsed / total if total else 0.0), total


def coerce_text_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[Coercion]:
    described = con.execute(f"DESCRIBE {quote_ident(table)}").fetchall()
    text_cols = [row[0] for row in described if str(row[1]).upper().startswith("VARCHAR")]
    applied: list[Coercion] = []
    for name in text_cols:
        col = quote_ident(name)
        rate, total = _rate(con, table, _numeric_expr(col), col)
        if total and rate >= PARSE_THRESHOLD:
            unit = _detect_unit(con, table, col)
            _replace(con, table, name, _numeric_expr(col), "DOUBLE")
            applied.append(Coercion(column=name, to_type="float", unit=unit))
            continue
        best = _best_temporal_format(con, table, col)
        if best:
            fmt, sql_type, ambiguous = best
            _replace(con, table, name, f"TRY_STRPTIME(trim({col}), {sql_string(fmt)})::{sql_type}", sql_type)
            applied.append(
                Coercion(column=name, to_type=sql_type.lower(), date_format=fmt, ambiguous=ambiguous)
            )
    _shrink_integer_doubles(con, table, [c.column for c in applied if c.to_type == "float"])
    return applied


def _detect_unit(con: duckdb.DuckDBPyConnection, table: str, col: str) -> str | None:
    row = con.execute(
        f"""SELECT
            avg(CASE WHEN {col} LIKE '%\\%%' ESCAPE '\\' THEN 1 ELSE 0 END),
            avg(CASE WHEN regexp_matches({col}, '[\\$€£¥]|USD|EUR|GBP|PKR|Rs') THEN 1 ELSE 0 END)
        FROM {quote_ident(table)} WHERE {col} IS NOT NULL"""
    ).fetchone()
    if not row:
        return None
    if (row[0] or 0) > 0.5:
        return "percent"
    if (row[1] or 0) > 0.5:
        return "currency"
    return None


def _best_temporal_format(
    con: duckdb.DuckDBPyConnection, table: str, col: str
) -> tuple[str, str, bool] | None:
    scores: list[tuple[float, str, str]] = []
    for fmt in _DATETIME_FORMATS:
        rate, total = _rate(con, table, f"TRY_STRPTIME(trim({col}), {sql_string(fmt)})", col)
        if total and rate >= PARSE_THRESHOLD:
            scores.append((rate, fmt, "TIMESTAMP"))
    for fmt in _DATE_FORMATS:
        rate, total = _rate(con, table, f"TRY_STRPTIME(trim({col}), {sql_string(fmt)})", col)
        if total and rate >= PARSE_THRESHOLD:
            scores.append((rate, fmt, "DATE"))
    if not scores:
        return None
    scores.sort(key=lambda s: -s[0])
    rate, fmt, sql_type = scores[0]
    ambiguous = any(
        s[0] == rate and {s[1], fmt} == {"%m/%d/%Y", "%d/%m/%Y"} for s in scores[1:]
    )
    return fmt, sql_type, ambiguous


def _replace(con: duckdb.DuckDBPyConnection, table: str, name: str, expr: str, sql_type: str) -> None:
    tmp = f"{name}__coerced"
    con.execute(f"ALTER TABLE {quote_ident(table)} ADD COLUMN {quote_ident(tmp)} {sql_type}")
    con.execute(f"UPDATE {quote_ident(table)} SET {quote_ident(tmp)} = {expr}")
    con.execute(f"ALTER TABLE {quote_ident(table)} DROP COLUMN {quote_ident(name)}")
    con.execute(f"ALTER TABLE {quote_ident(table)} RENAME COLUMN {quote_ident(tmp)} TO {quote_ident(name)}")


def _shrink_integer_doubles(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> None:
    for name in columns:
        col = quote_ident(name)
        row = con.execute(
            f"SELECT count(*) FILTER (WHERE {col} IS NOT NULL AND {col} <> floor({col})), "
            f"max(abs({col})) FROM {quote_ident(table)}"
        ).fetchone()
        if row and row[0] == 0 and (row[1] is None or row[1] < 9e15):
            con.execute(f"ALTER TABLE {quote_ident(table)} ALTER COLUMN {col} TYPE BIGINT")


def reorder_columns(con: duckdb.DuckDBPyConnection, table: str, order: list[str]) -> None:
    """Coercion appends replaced columns at the end; restore the original column order."""
    current = [row[0] for row in con.execute(f"DESCRIBE {quote_ident(table)}").fetchall()]
    if current == order:
        return
    select_list = ", ".join(quote_ident(c) for c in order if c in current)
    tmp = f"{table}__ordered"
    con.execute(f"CREATE TABLE {quote_ident(tmp)} AS SELECT {select_list} FROM {quote_ident(table)}")
    con.execute(f"DROP TABLE {quote_ident(table)}")
    con.execute(f"ALTER TABLE {quote_ident(tmp)} RENAME TO {quote_ident(table)}")
