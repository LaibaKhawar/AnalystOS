"""Dataset profiling, computed inside DuckDB (works on large tables without loading them into pandas)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import duckdb

from app.services.ingestion.naming import quote_ident

_EXACT_QUANTILE_MAX_ROWS = 2_000_000
_INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|system prompt|you are now|"
    r"disregard .{0,30}instructions|reveal .{0,40}(secret|password|environment|env|api key)|"
    r"os\.environ|<\s*/?\s*(system|assistant)\s*>|BEGIN (SYSTEM|PROMPT))",
    re.IGNORECASE,
)
_EMAIL = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"
_PHONE = r"^\+?[\d\s().-]{9,20}$"
_DATE_SHAPE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}")


def logical_type(physical: str) -> str:
    p = physical.upper()
    if p in {"BOOLEAN", "BOOL"}:
        return "boolean"
    if any(
        p.startswith(t)
        for t in (
            "TINYINT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "HUGEINT",
            "UTINYINT",
            "USMALLINT",
            "UINTEGER",
            "UBIGINT",
            "INT",
        )
    ):
        return "integer"
    if any(p.startswith(t) for t in ("DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC")):
        return "float"
    if p == "DATE":
        return "date"
    if p.startswith("TIMESTAMP") or p.startswith("DATETIME"):
        return "datetime"
    if p.startswith("TIME"):
        return "time"
    return "string"


@dataclass
class ColumnProfile:
    name: str
    physical_type: str
    inferred_type: str
    stats: dict[str, Any] = field(default_factory=dict)
    role: str = "other"
    flags: list[str] = field(default_factory=list)


@dataclass
class TableProfile:
    name: str
    row_count: int
    columns: list[ColumnProfile]
    table: dict[str, Any]


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def profile_table(con: duckdb.DuckDBPyConnection, table: str) -> TableProfile:
    t = quote_ident(table)
    row_count = int(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])  # type: ignore[index]
    described = con.execute(f"DESCRIBE {t}").fetchall()
    columns: list[ColumnProfile] = []
    for name, physical, *_ in described:
        columns.append(_profile_column(con, table, name, str(physical), row_count))

    col_list = ", ".join(quote_ident(c.name) for c in columns)
    duplicate_rows = 0
    if row_count and columns:
        duplicate_rows = int(
            con.execute(
                f"SELECT coalesce(sum(n - 1), 0) FROM (SELECT count(*) AS n FROM {t} GROUP BY {col_list})"
            ).fetchone()[0]  # type: ignore[index]
        )
    for column in columns:
        column.role = infer_role(column, row_count)

    missing_cells = sum(int(c.stats.get("null_count", 0)) for c in columns)
    total_cells = max(1, row_count * max(1, len(columns)))
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} fully duplicated row(s)")
    constant = [c.name for c in columns if c.stats.get("distinct_count") == 1 and row_count > 1]
    if constant:
        warnings.append(f"Constant column(s): {', '.join(constant)}")
    injected = [c.name for c in columns if "possible_prompt_injection" in c.flags]
    if injected:
        warnings.append(
            f"Column(s) {', '.join(injected)} contain text that looks like instructions to an AI. "
            "It is treated strictly as data."
        )
    high_missing = [c.name for c in columns if (c.stats.get("missing_pct") or 0) >= 30]
    if high_missing:
        warnings.append(f"High missing rate (>=30%) in: {', '.join(high_missing)}")

    summary = {
        "row_count": row_count,
        "column_count": len(columns),
        "duplicate_rows": duplicate_rows,
        "missing_cells_pct": round(100 * missing_cells / total_cells, 2),
        "constant_columns": constant,
        "identifier_columns": [c.name for c in columns if c.role == "identifier"],
        "metric_columns": [c.name for c in columns if c.role == "metric"],
        "dimension_columns": [c.name for c in columns if c.role == "dimension"],
        "time_columns": [c.name for c in columns if c.role == "time"],
        "text_columns": [c.name for c in columns if c.role == "text"],
        "warnings": warnings,
    }
    return TableProfile(name=table, row_count=row_count, columns=columns, table=summary)


def _profile_column(
    con: duckdb.DuckDBPyConnection, table: str, name: str, physical: str, row_count: int
) -> ColumnProfile:
    t, c = quote_ident(table), quote_ident(name)
    kind = logical_type(physical)
    base = con.execute(f"SELECT count({c}), count(DISTINCT {c}) FROM {t}").fetchone() or (0, 0)
    non_null, distinct = int(base[0]), int(base[1])
    stats: dict[str, Any] = {
        "count": non_null,
        "null_count": row_count - non_null,
        "missing_pct": round(100 * (row_count - non_null) / row_count, 2) if row_count else 0.0,
        "distinct_count": distinct,
        "unique_ratio": round(distinct / non_null, 4) if non_null else 0.0,
    }
    flags: list[str] = []
    examples = con.execute(f"SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL LIMIT 5").fetchall()
    stats["examples"] = [_clean(r[0]) for r in examples]

    if kind in {"integer", "float"} and non_null:
        q = "quantile_cont" if row_count <= _EXACT_QUANTILE_MAX_ROWS else "approx_quantile"
        row = con.execute(
            f"""SELECT min({c}), max({c}), avg({c}), {q}({c}, 0.5), stddev_samp({c}),
                       {q}({c}, 0.25), {q}({c}, 0.75), sum(CASE WHEN {c} = 0 THEN 1 ELSE 0 END),
                       sum(CASE WHEN {c} < 0 THEN 1 ELSE 0 END), sum({c})
                FROM {t}"""
        ).fetchone()
        assert row is not None
        mn, mx, mean, median, std, q1, q3, zeros, negatives, total = row
        stats.update(
            min=_clean(mn),
            max=_clean(mx),
            mean=_clean(mean),
            median=_clean(median),
            std=_clean(std),
            q1=_clean(q1),
            q3=_clean(q3),
            zeros=int(zeros or 0),
            negatives=int(negatives or 0),
            sum=_clean(total),
        )
        if q1 is not None and q3 is not None:
            iqr = float(q3) - float(q1)
            low, high = float(q1) - 1.5 * iqr, float(q3) + 1.5 * iqr
            outliers = con.execute(f"SELECT count(*) FROM {t} WHERE {c} < ? OR {c} > ?", [low, high]).fetchone()
            stats["outlier_count_iqr"] = int(outliers[0]) if outliers else 0
            stats["outlier_bounds"] = [_clean(low), _clean(high)]
            if iqr > 0:
                extremes = con.execute(
                    f"SELECT {c} FROM {t} WHERE {c} < ? OR {c} > ? ORDER BY abs({c} - ?) DESC LIMIT 5",
                    [low, high, float(median or 0)],
                ).fetchall()
                stats["suspicious_values"] = [_clean(r[0]) for r in extremes]
    elif kind in {"date", "datetime"} and non_null:
        row = con.execute(f"SELECT min({c}), max({c}) FROM {t}").fetchone()
        assert row is not None
        stats["min"], stats["max"] = _clean(row[0]), _clean(row[1])
        span = con.execute(f"SELECT date_diff('day', min({c})::DATE, max({c})::DATE) FROM {t}").fetchone()
        stats["span_days"] = int(span[0]) if span and span[0] is not None else 0
        stats["granularity"] = _granularity(stats["span_days"], distinct)
    elif kind == "boolean" and non_null:
        row = con.execute(f"SELECT avg(CASE WHEN {c} THEN 1.0 ELSE 0.0 END) FROM {t}").fetchone()
        stats["true_ratio"] = _clean(row[0]) if row else None
    elif kind == "string" and non_null:
        row = con.execute(f"SELECT min(length({c})), max(length({c})), avg(length({c})) FROM {t}").fetchone()
        assert row is not None
        stats.update(min_length=int(row[0] or 0), max_length=int(row[1] or 0), avg_length=_clean(row[2]))
        top = con.execute(
            f"SELECT {c}, count(*) AS n FROM {t} WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY n DESC, 1 LIMIT 10"
        ).fetchall()
        stats["top_values"] = [{"value": r[0], "count": int(r[1])} for r in top]
        sample = [
            r[0] for r in con.execute(f"SELECT {c} FROM {t} WHERE {c} IS NOT NULL USING SAMPLE 2000 ROWS").fetchall()
        ]
        matches = con.execute(
            f"SELECT count(*) FROM {t} WHERE regexp_matches({c}, ?, 'i')", [_INJECTION_PATTERNS.pattern]
        ).fetchone()
        if any(_INJECTION_PATTERNS.search(str(v)) for v in sample) or (matches and matches[0]):
            flags.append("possible_prompt_injection")
        if sample:
            emails = sum(bool(re.match(_EMAIL, str(v))) for v in sample) / len(sample)
            phones = sum(
                bool(re.match(_PHONE, str(v)))
                and not _DATE_SHAPE.match(str(v))
                and sum(ch.isdigit() for ch in str(v)) >= 9
                for v in sample
            ) / len(sample)
            if emails > 0.6:
                flags.append("pii_email")
            if phones > 0.6:
                flags.append("pii_phone")
    if distinct == 1 and row_count > 1:
        flags.append("constant")
    return ColumnProfile(name=name, physical_type=physical, inferred_type=kind, stats=stats, flags=flags)


def _granularity(span_days: int, distinct: int) -> str:
    if distinct <= 1:
        return "single"
    avg_gap = span_days / max(1, distinct - 1)
    if avg_gap < 0.5:
        return "intraday"
    if avg_gap <= 1.5:
        return "daily"
    if avg_gap <= 8:
        return "weekly"
    if avg_gap <= 35:
        return "monthly"
    if avg_gap <= 100:
        return "quarterly"
    return "yearly"


_ID_NAME = re.compile(r"(^id$|_id$|^id_|uuid|guid|_key$|^key$|_code$|^code$|_no$|_number$|sku$)", re.I)
_TIME_NAME = re.compile(r"(year|month|quarter|week|day|date|period)", re.I)


def infer_role(column: ColumnProfile, row_count: int) -> str:
    stats, kind = column.stats, column.inferred_type
    distinct = int(stats.get("distinct_count", 0))
    unique_ratio = float(stats.get("unique_ratio", 0))
    name = column.name
    if kind in {"date", "datetime"}:
        return "time"
    if _ID_NAME.search(name) and (unique_ratio > 0.5 or kind == "string"):
        return "identifier"
    if kind == "boolean":
        return "dimension"
    if kind in {"integer", "float"}:
        if kind == "integer" and re.fullmatch(r"(year|fiscal_year|yr)", name, re.I):
            return "time"
        if kind == "integer" and unique_ratio == 1.0 and row_count > 50 and _is_sequence(stats):
            return "identifier"
        if kind == "integer" and distinct <= 12 and _TIME_NAME.search(name):
            return "time"
        if kind == "integer" and distinct <= 5 and row_count > 50 and not _looks_like_measure(name):
            return "dimension"
        return "metric"
    if kind == "string":
        dimension_cap = max(30, int(0.05 * row_count))
        if distinct <= dimension_cap or unique_ratio < 0.2:
            return "dimension"
        if unique_ratio > 0.9 and float(stats.get("avg_length") or 0) < 40:
            return "identifier"
        return "text"
    return "other"


def _is_sequence(stats: dict[str, Any]) -> bool:
    mn, mx, count = stats.get("min"), stats.get("max"), stats.get("count")
    return bool(mn is not None and mx is not None and count and (float(mx) - float(mn) + 1) == count)


def _looks_like_measure(name: str) -> bool:
    return bool(re.search(r"(amount|revenue|sales|price|cost|qty|quantity|units|count|total|score|rating)", name, re.I))
