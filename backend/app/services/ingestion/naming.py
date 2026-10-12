"""Turn arbitrary column/sheet names ("Revenue ($)", "2026 Sales", "Customer ID") into safe SQL identifiers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_SYMBOL_WORDS = {"$": " usd ", "€": " eur ", "£": " gbp ", "%": " pct ", "#": " num ", "&": " and ", "+": " plus "}
_RESERVED = {
    "select",
    "from",
    "where",
    "group",
    "order",
    "by",
    "limit",
    "table",
    "join",
    "on",
    "as",
    "and",
    "or",
    "not",
    "null",
    "case",
    "when",
    "then",
    "else",
    "end",
    "union",
    "all",
    "distinct",
    "having",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "with",
    "in",
    "is",
    "into",
    "values",
}


def to_identifier(raw: object, fallback: str = "column") -> str:
    text = str(raw if raw is not None else "").strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    for symbol, word in _SYMBOL_WORDS.items():
        text = text.replace(symbol, word)
    # camelCase -> camel_case
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    text = re.sub(r"_+", "_", text)
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"col_{text}"
    if text in _RESERVED:
        text = f"{text}_"
    return text[:63]


def unique_identifiers(raw_names: Sequence[object], fallback: str = "column") -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, raw in enumerate(raw_names):
        base = to_identifier(raw, fallback=f"{fallback}_{index + 1}")
        name = base
        while name in seen:
            seen[base] += 1
            name = f"{base}_{seen[base]}"
        seen.setdefault(name, 1)
        seen.setdefault(base, 1)
        result.append(name)
    return result


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
