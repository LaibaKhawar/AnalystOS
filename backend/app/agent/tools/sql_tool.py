"""execute_sql: run model-written SQL after AST validation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.context import ToolContext
from app.agent.tools.base import Tool, ToolResult
from app.agent.tools.common import compact_table, query, rows_findings


class ExecuteSQLInput(BaseModel):
    sql: str = Field(..., description="One read-only SELECT statement in the source's SQL dialect")
    purpose: str = Field("", description="What this query computes, in a few words")


class ExecuteSQL(Tool):
    name = "execute_sql"
    description = (
        "Run one read-only SELECT (CTEs, joins, window functions allowed). It is validated against the "
        "schema before execution; results are capped. Prefer the specialised tools for standard "
        "aggregations; use SQL for custom logic. Aggregate in SQL: do not select raw rows."
    )
    Input = ExecuteSQLInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ExecuteSQLInput)
        result, sql_id = query(ctx, args.sql)
        names = [c["name"] for c in result.columns]
        table = ctx.save_result_table(
            args.purpose or "SQL result",
            result.columns,
            result.rows,
            truncated=result.truncated,
            source={
                "type": "sql",
                "sql_execution_id": sql_id,
                "sql": result.executed_sql,
                "dialect": ctx.engine.dialect,
            },
        )
        findings = rows_findings(args.purpose or "Query result", names, result.rows, limit=30)
        for finding in findings:  # the purpose text is model-written; the verifier checks periods against the SQL
            finding.payload["scope_text"] = result.executed_sql
        truncated = " (truncated)" if result.truncated else ""
        summary = f"result_id={table.id} rows={result.row_count}{truncated}\n{compact_table(names, result.rows)}"
        if result.row_count == 0:
            summary += "\nThe query returned no rows: check filters, value spelling and date ranges."
        return ToolResult(
            summary=summary,
            data={"columns": result.columns, "row_count": result.row_count},
            result_table_id=table.id,
            findings=findings,
        )
