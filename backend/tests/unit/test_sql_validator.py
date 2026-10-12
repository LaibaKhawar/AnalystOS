from __future__ import annotations

import pytest

from app.services.sql.validator import Catalog, SQLLimits, validate_sql

CATALOG = Catalog(
    tables={
        "sales": {"date": "DATE", "region": "VARCHAR", "revenue": "DOUBLE", "customer_email": "VARCHAR"},
        "products": {"product": "VARCHAR", "category": "VARCHAR"},
    },
    restricted_columns={("sales", "customer_email")},
)

ALLOWED = [
    "SELECT region, SUM(revenue) AS rev FROM sales GROUP BY region ORDER BY rev DESC",
    "WITH m AS (SELECT date_trunc('month', date) AS m, SUM(revenue) AS r FROM sales GROUP BY 1) "
    "SELECT m, r, LAG(r) OVER (ORDER BY m) AS prev FROM m",
    "SELECT s.region, p.category FROM sales s JOIN products p ON s.region = p.product",
    "SELECT CASE WHEN revenue > 100 THEN 'high' ELSE 'low' END AS band, COUNT(*) FROM sales GROUP BY 1",
    "SELECT region FROM sales UNION SELECT category FROM products",
    "SELECT COUNT(DISTINCT customer_email) FROM sales",
    "SELECT region, AVG(revenue) FROM sales WHERE date >= DATE '2026-01-01' GROUP BY region HAVING AVG(revenue) > 5",
    "SELECT * FROM (SELECT region, revenue FROM sales) t WHERE revenue > 0",
]

BLOCKED = [
    ("DELETE FROM sales", "statement_type"),
    ("DROP TABLE sales", "statement_type"),
    ("UPDATE sales SET revenue = 0", "statement_type"),
    ("INSERT INTO sales VALUES (1)", "statement_type"),
    ("CREATE TABLE x AS SELECT * FROM products", "statement_type"),
    ("ALTER TABLE sales ADD COLUMN x INT", "statement_type"),
    ("TRUNCATE TABLE sales", "statement_type"),
    ("GRANT ALL ON sales TO bob", "statement_type"),
    ("COPY sales TO '/tmp/x.csv'", "statement_type"),
    ("CALL some_proc()", "statement_type"),
    ("PRAGMA database_list", "statement_type"),
    ("ATTACH 'other.db'", "statement_type"),
    ("SET enable_external_access = true", "statement_type"),
    ("INSTALL httpfs", "statement_type"),
    ("SELECT 1; DROP TABLE sales", "multiple_statements"),
    ("SELECT * INTO backup FROM products", "forbidden_operation"),
    ("SELECT * FROM products FOR UPDATE", "forbidden_operation"),
    ("SELECT * FROM read_parquet('/etc/passwd')", "forbidden_function"),
    ("SELECT * FROM read_csv_auto('/etc/hosts')", "forbidden_function"),
    ("SELECT * FROM '/etc/passwd.csv'", "forbidden_table"),
    ("SELECT getenv('HOME')", "forbidden_function"),
    ("SELECT pg_sleep(10)", "forbidden_function"),
    ("SELECT pg_read_file('/etc/passwd')", "forbidden_function"),
    ("SELECT current_setting('data_directory')", "forbidden_function"),
    ("SELECT * FROM salez", "unknown_table"),
    ("SELECT * FROM information_schema.tables", "unknown_table"),
    ("SELECT regions FROM sales", "unknown_column"),
    ("SELECT customer_email FROM sales", "restricted_column"),
    ("SELECT * FROM sales", "restricted_column"),
    ("", "empty"),
    ("SELEC region FROM sales", "syntax"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries(sql: str) -> None:
    result = validate_sql(sql, "duckdb", CATALOG)
    assert result.ok, result.errors
    assert result.safe_sql and "LIMIT" in result.safe_sql.upper()


@pytest.mark.parametrize(("sql", "kind"), BLOCKED)
def test_blocked_queries(sql: str, kind: str) -> None:
    result = validate_sql(sql, "duckdb", CATALOG)
    assert not result.ok
    assert result.errors[0]["kind"] == kind, result.errors


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "sqlite"])
def test_dml_in_cte_blocked_across_dialects(dialect: str) -> None:
    sql = "WITH d AS (DELETE FROM sales RETURNING *) SELECT * FROM d"
    result = validate_sql(sql, dialect, CATALOG)
    assert not result.ok


def test_unknown_column_suggestions() -> None:
    result = validate_sql("SELECT regions, SUM(revenue) FROM sales GROUP BY regions", "duckdb", CATALOG)
    assert result.errors[0]["suggestions"] == ["region"]


def test_row_limit_enforced_and_kept_when_smaller() -> None:
    wide = validate_sql("SELECT region FROM sales LIMIT 100000", "duckdb", CATALOG, SQLLimits(max_rows=50))
    assert wide.safe_sql is not None and wide.safe_sql.endswith("LIMIT 51")
    small = validate_sql("SELECT region FROM sales LIMIT 10", "duckdb", CATALOG, SQLLimits(max_rows=50))
    assert small.safe_sql is not None and small.safe_sql.endswith("LIMIT 10")


def test_join_limit() -> None:
    joins = " ".join(f"JOIN products p{i} ON p{i}.product = s.region" for i in range(4))
    result = validate_sql(f"SELECT s.region FROM sales s {joins}", "duckdb", CATALOG, SQLLimits(max_joins=3))
    assert not result.ok and result.errors[0]["kind"] == "too_complex"


def test_allowlist() -> None:
    catalog = Catalog(tables=CATALOG.tables, allowed_tables={"products"})
    assert not validate_sql("SELECT region FROM sales", "duckdb", catalog).ok
    assert validate_sql("SELECT category FROM products", "duckdb", catalog).ok
