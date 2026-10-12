"""AST-based SQL safety validation (sqlglot). Regex is never used as the security boundary.

A statement is accepted only if:
  * it parses as exactly one statement,
  * the root is a SELECT or a set operation of SELECTs (UNION / INTERSECT / EXCEPT, with optional CTEs),
  * no node anywhere in the tree is DML/DDL/DCL or a vendor command (this catches DML inside CTEs,
    SELECT ... INTO, FOR UPDATE locks, COPY, PRAGMA, ATTACH, SET, CALL, ...),
  * no forbidden function is called (file access, sleep, settings, remote access, table functions),
  * every referenced table exists in the catalog and is on the allowlist, every column resolves,
  * restricted (PII) columns are only used inside COUNT aggregates,
  * join count and subquery depth are within configured limits.

The validator then rewrites the statement with an enforced row limit.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

ALLOWED_ROOTS: tuple[type[exp.Expression], ...] = (exp.Select, exp.Union, exp.Intersect, exp.Except)

_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable", "Command",
    "Copy", "Grant", "Revoke", "Into", "Lock", "Pragma", "Set", "SetItem", "Attach", "Detach", "Install", "Load",
    "Use", "Transaction", "Commit", "Rollback", "Describe", "Show", "Analyze", "Kill", "Summarize", "Export",
    "LoadData", "Refresh", "Cache", "Uncache", "Comment", "Execute", "ExecuteSql",
)
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)

FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "sleep", "benchmark", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "lo_get", "lo_put", "dblink", "dblink_exec", "dblink_connect", "load_file",
    "getenv", "current_setting", "set_config", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
    "pg_rotate_logfile", "query", "query_table", "glob", "sniff_csv", "system", "shell", "sys_exec", "sys_eval",
    "xp_cmdshell", "http_get", "http_post", "pg_advisory_lock", "pg_notify", "txid_current", "nextval", "setval",
    "make_table", "load_extension", "writefile", "readfile", "edit", "fts5", "pg_logical_emit_message",
}
FORBIDDEN_PREFIXES = ("read_", "pg_read", "pg_ls", "pg_stat", "lo_", "dblink", "duckdb_", "pragma_", "http",
                      "sys_", "parquet_", "iceberg_", "delta_", "sqlite_", "mysql_", "postgres_", "pg_file")
AGGREGATE_SAFE_FOR_PII = (exp.Count, exp.ApproxDistinct)


@dataclass
class SQLLimits:
    max_rows: int = 5000
    max_joins: int = 6
    max_subquery_depth: int = 4
    max_nodes: int = 3000


@dataclass
class Catalog:
    """Known tables -> {column: type}. Keys are lower-cased identifiers."""

    tables: dict[str, dict[str, str]]
    allowed_tables: set[str] | None = None
    restricted_columns: set[tuple[str, str]] = field(default_factory=set)  # (table, column)

    def schema_mapping(self) -> dict[str, dict[str, str]]:
        return {t: {c: (ty or "TEXT") for c, ty in cols.items()} for t, cols in self.tables.items()}


@dataclass
class ValidationResult:
    ok: bool
    sql: str
    dialect: str
    safe_sql: str | None = None
    statement_type: str | None = None
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied_limit: int | None = None

    def error_message(self) -> str:
        return "; ".join(e["message"] for e in self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "statement_type": self.statement_type, "tables": self.tables, "columns": self.columns,
            "errors": self.errors, "warnings": self.warnings, "applied_limit": self.applied_limit,
        }


def _fail(result: ValidationResult, kind: str, message: str, **extra: Any) -> ValidationResult:
    result.ok = False
    result.errors.append({"kind": kind, "message": message, **extra})
    return result


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    try:
        return node.sql_name().lower()
    except Exception:
        return node.__class__.__name__.lower()


def _subquery_depth(node: exp.Expression) -> int:
    depth = 0
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.Subquery | exp.CTE):
            depth += 1
        parent = parent.parent
    return depth


def suggest(name: str, candidates: list[str]) -> list[str]:
    return difflib.get_close_matches(name.lower(), [c.lower() for c in candidates], n=3, cutoff=0.6)


def validate_sql(sql: str, dialect: str, catalog: Catalog, limits: SQLLimits | None = None) -> ValidationResult:
    limits = limits or SQLLimits()
    result = ValidationResult(ok=True, sql=sql, dialect=dialect)
    text = (sql or "").strip()
    if not text:
        return _fail(result, "empty", "The SQL statement is empty")
    if len(text) > 20_000:
        return _fail(result, "too_long", "The SQL statement is too long")

    try:
        statements = [s for s in sqlglot.parse(text, read=dialect) if s is not None]
    except ParseError as exc:
        first = exc.errors[0] if exc.errors else {}
        return _fail(result, "syntax", f"SQL syntax error: {first.get('description', str(exc))[:200]}")
    except Exception as exc:  # sqlglot can raise TokenError etc.
        return _fail(result, "syntax", f"SQL could not be parsed: {str(exc)[:200]}")

    if len(statements) != 1:
        return _fail(result, "multiple_statements", f"Exactly one statement is allowed (found {len(statements)})")
    tree = statements[0]
    result.statement_type = tree.key.upper()

    if not isinstance(tree, ALLOWED_ROOTS):
        return _fail(result, "statement_type",
                     f"Only read-only SELECT queries are allowed ({tree.key.upper()} is blocked)")

    node_count = 0
    for node in tree.walk():
        node_count += 1
        if isinstance(node, FORBIDDEN_NODES):
            return _fail(result, "forbidden_operation",
                         f"Forbidden operation inside the query: {node.key.upper()}")
        if isinstance(node, exp.Func):
            fname = _function_name(node)
            if fname in FORBIDDEN_FUNCTIONS or fname.startswith(FORBIDDEN_PREFIXES):
                return _fail(result, "forbidden_function", f"Function '{fname}' is not allowed")
        if isinstance(node, exp.Table) and isinstance(node.this, exp.Func | exp.Literal):
            return _fail(result, "forbidden_function", "Table functions and file paths are not allowed in FROM")
    if node_count > limits.max_nodes:
        return _fail(result, "too_complex", "The query is too complex")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    referenced: list[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name or name in cte_names:
            continue
        if re.search(r"[/\\]|\.(csv|parquet|json|txt|db|duckdb|sqlite)$", name):
            return _fail(result, "forbidden_table", "File paths cannot be queried directly")
        if name not in catalog.tables:
            options = suggest(name, list(catalog.tables))
            hint = f" Did you mean: {', '.join(options)}?" if options else ""
            return _fail(result, "unknown_table", f"Unknown table '{table.name}'.{hint}",
                         table=table.name, suggestions=options, available=sorted(catalog.tables))
        if catalog.allowed_tables is not None and name not in catalog.allowed_tables:
            return _fail(result, "table_not_allowed", f"Table '{table.name}' is not on this connection's allowlist")
        referenced.append(name)
    result.tables = sorted(set(referenced))

    joins = list(tree.find_all(exp.Join))
    if len(joins) > limits.max_joins:
        return _fail(result, "too_complex", f"Too many joins ({len(joins)} > {limits.max_joins})")
    for join in joins:
        if not join.args.get("on") and not join.args.get("using") and (join.kind or "").upper() != "CROSS" \
                and not isinstance(join.this, exp.Unnest | exp.Lateral):
            result.warnings.append("A join without an ON/USING condition produces a cartesian product")
    for sub in tree.find_all(exp.Subquery, exp.CTE):
        if _subquery_depth(sub) + 1 > limits.max_subquery_depth:
            return _fail(result, "too_complex", f"Subqueries nested deeper than {limits.max_subquery_depth} levels")

    # Column resolution: qualify against the catalog so misspelled columns fail before execution.
    qualified_ok = True
    try:
        qualified = qualify(
            tree.copy(), schema=catalog.schema_mapping(), dialect=dialect, validate_qualify_columns=True,
            quote_identifiers=False, identify=False,
        )
    except OptimizeError as exc:
        message = str(exc)
        match = re.search(r"[Cc]olumn '?\"?([\w ]+?)\"?'? could not be resolved", message)
        if match:
            missing = match.group(1)
            candidates = sorted({c for t in (result.tables or catalog.tables) for c in catalog.tables.get(t, {})})
            options = suggest(missing, candidates)
            hint = f" Did you mean: {', '.join(options)}?" if options else ""
            return _fail(result, "unknown_column", f"Unknown column '{missing}'.{hint}", column=missing,
                         suggestions=options, available=candidates[:60])
        result.warnings.append(f"Column resolution was partial: {message[:160]}")
        qualified, qualified_ok = tree, False
    except Exception as exc:  # pragma: no cover - defensive: optimizer edge cases on exotic syntax
        result.warnings.append(f"Column resolution skipped: {str(exc)[:160]}")
        qualified, qualified_ok = tree, False

    columns: set[str] = set()
    for column in qualified.find_all(exp.Column):
        table_alias = column.table.lower() if column.table else ""
        columns.add(f"{table_alias}.{column.name}" if table_alias else column.name)
    result.columns = sorted(columns)

    if catalog.restricted_columns:
        violation = _restricted_violation(qualified, tree, catalog, stars_expanded=qualified_ok)
        if violation:
            return _fail(result, "restricted_column",
                         f"Column '{violation}' is marked sensitive (PII); it can only be counted, not returned")

    safe_tree = _enforce_limit(tree, limits.max_rows, result)
    result.safe_sql = safe_tree.sql(dialect=dialect)
    return result


def _restricted_violation(qualified: exp.Expression, original: exp.Expression, catalog: Catalog, *,
                          stars_expanded: bool) -> str | None:
    restricted_names = {c for _, c in catalog.restricted_columns}
    alias_to_table: dict[str, str] = {}
    for table in qualified.find_all(exp.Table):
        alias_to_table[(table.alias_or_name or table.name).lower()] = table.name.lower()
    for column in qualified.find_all(exp.Column):
        name = column.name.lower()
        if name not in restricted_names:
            continue
        table = alias_to_table.get(column.table.lower(), column.table.lower()) if column.table else ""
        if table and (table, name) not in catalog.restricted_columns:
            continue
        inside_count = column.find_ancestor(*AGGREGATE_SAFE_FOR_PII) is not None
        if not inside_count:
            return column.name
    # Qualification expands SELECT * into concrete columns (checked above). If it failed, be conservative:
    # a star over a table with restricted columns could return them.
    if not stars_expanded and any(isinstance(s, exp.Star) for s in original.find_all(exp.Star)):
        star_tables = {t.name.lower() for t in original.find_all(exp.Table)}
        for table, column_name in catalog.restricted_columns:
            if table in star_tables:
                parent_selects = [s for s in original.find_all(exp.Star) if s.find_ancestor(exp.Count) is None]
                if parent_selects:
                    return column_name
    return None


def _enforce_limit(tree: exp.Expression, max_rows: int, result: ValidationResult) -> exp.Expression:
    fetch_cap = max_rows + 1  # +1 lets the executor detect truncation
    tree = tree.copy()
    if isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        existing = _literal_int(limit.expression) if isinstance(limit, exp.Limit) else None
        if existing is None or existing > fetch_cap:
            tree = tree.limit(fetch_cap)
            result.applied_limit = max_rows
        return tree
    wrapped = exp.select("*").from_(tree.subquery("_q")).limit(fetch_cap)
    result.applied_limit = max_rows
    return wrapped


def _literal_int(node: exp.Expression | None) -> int | None:
    if isinstance(node, exp.Literal) and node.is_int:
        return int(node.this)
    return None
