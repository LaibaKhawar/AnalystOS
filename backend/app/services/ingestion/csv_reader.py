"""CSV ingestion into DuckDB: encoding detection, delimiter/header sniffing, malformed-row accounting.

The file is streamed by DuckDB, so large files never need to fit in pandas memory.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
from collections import Counter
from pathlib import Path

import duckdb
from charset_normalizer import from_bytes

from app.core.errors import IngestionError
from app.services.ingestion.naming import quote_ident, sql_string, unique_identifiers
from app.services.ingestion.types import LoadedTable

_UTF8_ALIASES = {"utf_8", "utf-8", "ascii", "utf_8_sig", "utf-8-sig"}
_SAMPLE_BYTES = 1_000_000


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:_SAMPLE_BYTES] if path.stat().st_size < 50_000_000 else _head(path)
    if not sample.strip():
        raise IngestionError("The file is empty")
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf_8_sig"
    try:
        sample.decode("utf-8")
        return "utf_8"
    except UnicodeDecodeError as exc:
        # A multi-byte character may be cut at the sample boundary.
        if exc.start >= len(sample) - 4:
            return "utf_8"
    if sample[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf_16"
    best = from_bytes(sample).best()
    # Statistical detectors are unreliable on short Western samples (latin-1 is often reported as
    # cp852/cp1250). Prefer cp1252 when it decodes cleanly unless the detector found a multi-byte codec.
    if best and best.encoding.replace("-", "_") in {"utf_16", "utf_32", "big5", "gb18030", "shift_jis", "euc_jp",
                                                     "euc_kr", "cp949", "gbk"}:
        return best.encoding
    try:
        sample.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return best.encoding if best else "latin_1"


def _head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(_SAMPLE_BYTES)


def ensure_utf8(path: Path, encoding: str, work_dir: Path) -> Path:
    if encoding.lower() in _UTF8_ALIASES:
        return path
    target = work_dir / f"{path.stem}.utf8.csv"
    with path.open("r", encoding=encoding, errors="replace", newline="") as src, target.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    return target


def load_csv(con: duckdb.DuckDBPyConnection, path: Path, table_name: str, work_dir: Path) -> LoadedTable:
    encoding = detect_encoding(path)
    source = ensure_utf8(path, encoding, work_dir)
    warnings: list[str] = []
    if source is not path:
        warnings.append(f"File was encoded as {encoding}; converted to UTF-8")

    delimiter, has_header, width = sniff_structure(source)
    staging = f"__staging_{table_name}"
    try:
        con.execute(
            f"""
            CREATE TABLE {quote_ident(staging)} AS
            SELECT * FROM read_csv(
                {sql_string(str(source))},
                delim = {sql_string(delimiter)},
                header = {str(has_header).lower()},
                auto_detect = true,
                sample_size = 20480,
                ignore_errors = true,
                store_rejects = true,
                null_padding = false,
                nullstr = ['', 'NA', 'N/A', 'null', 'NULL', 'None', 'nan', 'NaN', '-', '#N/A'],
                normalize_names = false
            )
            """
        )
    except duckdb.Error as exc:
        raise IngestionError(f"Could not read the CSV file: {_short(exc)}") from exc

    rejected = 0
    try:
        rejected = int(con.execute("SELECT count(DISTINCT line) FROM reject_errors").fetchone()[0])  # type: ignore[index]
    except duckdb.Error:
        rejected = 0
    if rejected:
        warnings.append(f"{rejected} malformed row(s) could not be parsed and were skipped")

    original = [d[0] for d in con.execute(f"SELECT * FROM {quote_ident(staging)} LIMIT 0").description or []]
    if not has_header:
        warnings.append("No header row detected; columns were named column_1, column_2, ...")
        original = [f"column_{i + 1}" for i in range(len(original))]
    names = unique_identifiers(original)
    select_list = ", ".join(
        f"{quote_ident(src)} AS {quote_ident(dst)}"
        for src, dst in zip(
            [d[0] for d in con.execute(f"SELECT * FROM {quote_ident(staging)} LIMIT 0").description or []],
            names,
            strict=True,
        )
    )
    con.execute(f"CREATE TABLE {quote_ident(table_name)} AS SELECT {select_list} FROM {quote_ident(staging)}")
    con.execute(f"DROP TABLE {quote_ident(staging)}")
    row_count = int(con.execute(f"SELECT count(*) FROM {quote_ident(table_name)}").fetchone()[0])  # type: ignore[index]
    if row_count == 0:
        raise IngestionError("The CSV file contains no data rows")
    return LoadedTable(
        name=table_name,
        display_name=path.stem,
        original_columns=[str(c) for c in original],
        columns=names,
        row_count=row_count,
        warnings=warnings,
        details={"encoding": encoding, "delimiter": delimiter, "has_header": has_header, "rejected_rows": rejected},
    )


def sniff_structure(path: Path, max_lines: int = 500) -> tuple[str, bool, int]:
    """Detect delimiter, header presence and the modal row width from the first lines of the file.

    DuckDB's sniffer is fast but a few malformed rows near the top can make it give up on types and
    headers; using the modal field count keeps the dominant structure and lets bad rows be rejected.
    """
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        lines = [line for _, line in zip(range(max_lines), handle, strict=False)]
    text = "".join(lines)
    if not text.strip():
        raise IngestionError("The file is empty")
    best: tuple[float, str, int] = (-1.0, ",", 1)
    for candidate in [",", ";", "\t", "|"]:
        rows = list(csv.reader(io.StringIO(text), delimiter=candidate))
        widths = [len(r) for r in rows if any(cell.strip() for cell in r)]
        if not widths:
            continue
        modal, count = Counter(widths).most_common(1)[0]
        if modal < 2:
            continue
        score = count / len(widths) + min(modal, 50) / 100
        if score > best[0]:
            best = (score, candidate, modal)
    _, delimiter, width = best
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if len(r) == width]
    return delimiter, _looks_like_header(rows), width


def _is_number(cell: str) -> bool:
    cleaned = re.sub(r"[\s$€£,%()]", "", cell)
    try:
        float(cleaned)
        return bool(cleaned)
    except ValueError:
        return False


def _looks_like_header(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return True
    first, rest = rows[0], rows[1:20]
    cells = [c.strip() for c in first]
    if any(not c for c in cells) and sum(1 for c in cells if not c) > len(cells) // 2:
        return False
    if len(set(cells)) != len(cells):
        return False
    numeric_header = sum(_is_number(c) for c in cells)
    numeric_body = sum(_is_number(c) for r in rest for c in r) / max(1, sum(len(r) for r in rest))
    # A header is mostly non-numeric text while the body below carries numbers somewhere.
    if numeric_header == 0 and numeric_body > 0:
        return True
    if numeric_header == 0:
        body_values = {c.strip() for r in rest for c in r}
        return not any(c in body_values for c in cells)
    return numeric_header < len(cells) * 0.25 and numeric_body > 0.25


def _short(exc: Exception) -> str:
    text = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return text[:300]
