"""Schema and profile inspection tools (read stored metadata; no raw rows are returned)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.context import ToolContext, fmt_number, render_schema
from app.agent.tools.base import FindingDraft, Tool, ToolResult


class NoArgs(BaseModel):
    pass


class TableName(BaseModel):
    table: str | None = Field(None, description="Table name; optional when the source has one table")


class ListTables(Tool):
    name = "list_tables"
    description = "List the tables (or sheets) in the selected data source with row and column counts."
    Input = NoArgs

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        tables = [{"table": t.name, "display_name": t.display_name, "rows": t.row_count, "columns": t.column_count}
                  for t in ctx.tables]
        lines = [f"{t['table']} ({t['display_name']}): {fmt_number(t['rows'])} rows, {t['columns']} columns"
                 for t in tables]
        findings = [FindingDraft(kind="stat", statement=f"Table {t['table']} has {fmt_number(t['rows'])} rows and "
                                                         f"{t['columns']} columns",
                                 values={"rows": t["rows"], "columns": t["columns"]}, entities=[t["table"]])
                    for t in tables]
        return ToolResult(summary="\n".join(lines), data={"tables": tables}, findings=findings)


class DescribeTable(Tool):
    name = "describe_table"
    description = "Describe one table: columns, inferred types, roles, semantic meaning with confidence, key stats."
    Input = TableName

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, TableName)
        table = ctx.table(args.table)
        columns = [{
            "name": c.name, "original_name": c.original_name, "type": c.inferred_type, "role": c.role,
            "semantic_type": c.semantic_type, "confidence": c.semantic_confidence, "pii": c.is_pii,
            "missing_pct": c.stats.get("missing_pct"), "distinct": c.stats.get("distinct_count"),
        } for c in table.columns]
        summary = "\n".join(
            f"{c['name']}: {c['type']} role={c['role']} meaning={c['semantic_type']} ({c['confidence']:.2f}) "
            f"missing={c['missing_pct']}% distinct={c['distinct']}" for c in columns)
        return ToolResult(summary=f"TABLE {table.name} ({fmt_number(table.row_count)} rows)\n{summary}",
                          data={"table": table.name, "columns": columns})


class InspectSchema(Tool):
    name = "inspect_schema"
    description = "Return the semantic schema: likely metrics, dimensions, time columns and identifiers per table."
    Input = NoArgs

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        semantic = {t.name: t.semantic for t in ctx.tables}
        return ToolResult(summary=render_schema(ctx.source), data={"semantic": semantic})


class ProfileDataset(Tool):
    name = "profile_dataset"
    description = ("Data-quality profile of a table: duplicates, missing values, constant columns, outliers and "
                   "warnings. Use before analysis when data quality could affect conclusions.")
    Input = TableName

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, TableName)
        table = ctx.table(args.table)
        profile = table.profile or {}
        findings = [
            FindingDraft(kind="stat", statement=f"Table {table.name} has {fmt_number(table.row_count)} rows, "
                                                 f"{table.column_count} columns and "
                                                 f"{fmt_number(profile.get('duplicate_rows', 0))} duplicated rows",
                         values={"rows": table.row_count, "columns": table.column_count,
                                 "duplicate_rows": profile.get("duplicate_rows", 0),
                                 "missing_cells_pct": profile.get("missing_cells_pct")}, entities=[table.name]),
        ]
        lines = [f"rows={fmt_number(table.row_count)} duplicates={profile.get('duplicate_rows', 0)} "
                 f"missing_cells={profile.get('missing_cells_pct')}%"]
        for column in table.columns:
            stats = column.stats or {}
            if stats.get("missing_pct"):
                findings.append(FindingDraft(
                    kind="stat", statement=f"Column {column.name} is {stats['missing_pct']}% missing "
                                           f"({fmt_number(stats.get('null_count'))} of {fmt_number(table.row_count)} rows)",
                    values={"missing_pct": stats["missing_pct"], "null_count": stats.get("null_count")},
                    entities=[column.name]))
            if stats.get("outlier_count_iqr"):
                lines.append(f"{column.name}: {stats['outlier_count_iqr']} IQR outliers, bounds "
                             f"{stats.get('outlier_bounds')}, extreme values {stats.get('suspicious_values')}")
                findings.append(FindingDraft(
                    kind="stat", statement=f"Column {column.name} has {fmt_number(stats['outlier_count_iqr'])} values "
                                           f"outside the IQR fences {stats.get('outlier_bounds')}",
                    values={"outlier_count": stats["outlier_count_iqr"]}, entities=[column.name]))
        lines.extend(f"warning: {w}" for w in profile.get("warnings", []))
        return ToolResult(summary="\n".join(lines), data={"profile": profile}, findings=findings)
