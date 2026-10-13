"""Schema and profile inspection tools (read stored metadata; no raw rows are returned)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.context import ToolContext, fmt_number, render_schema
from app.agent.tools.base import FindingDraft, Tool, ToolError, ToolResult
from app.db.models import ColumnMetadata


class NoArgs(BaseModel):
    pass


class TableName(BaseModel):
    table: str | None = Field(None, description="Table name; optional when the source has one table")


class ListTables(Tool):
    name = "list_tables"
    description = "List the tables (or sheets) in the selected data source with row and column counts."
    Input = NoArgs

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        tables = [
            {"table": t.name, "display_name": t.display_name, "rows": t.row_count, "columns": t.column_count}
            for t in ctx.tables
        ]
        lines = [
            f"{t['table']} ({t['display_name']}): {fmt_number(t['rows'])} rows, {t['columns']} columns" for t in tables
        ]
        findings = [
            FindingDraft(
                kind="stat",
                statement=f"Table {t['table']} has {fmt_number(t['rows'])} rows and {t['columns']} columns",
                values={"rows": t["rows"], "columns": t["columns"]},
                entities=[str(t["table"])],
            )
            for t in tables
        ]
        return ToolResult(summary="\n".join(lines), data={"tables": tables}, findings=findings)


class DescribeTable(Tool):
    name = "describe_table"
    description = "Describe one table: columns, inferred types, roles, semantic meaning with confidence, key stats."
    Input = TableName

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, TableName)
        table = ctx.table(args.table)
        columns = [
            {
                "name": c.name,
                "original_name": c.original_name,
                "type": c.inferred_type,
                "role": c.role,
                "semantic_type": c.semantic_type,
                "confidence": c.semantic_confidence,
                "pii": c.is_pii,
                "missing_pct": c.stats.get("missing_pct"),
                "distinct": c.stats.get("distinct_count"),
            }
            for c in table.columns
        ]
        summary = "\n".join(
            f"{c['name']}: {c['type']} role={c['role']} meaning={c['semantic_type']} ({c['confidence']:.2f}) "
            f"missing={c['missing_pct']}% distinct={c['distinct']}"
            for c in columns
        )
        return ToolResult(
            summary=f"TABLE {table.name} ({fmt_number(table.row_count)} rows)\n{summary}",
            data={"table": table.name, "columns": columns},
        )


class InspectSchema(Tool):
    name = "inspect_schema"
    description = "Return the semantic schema: likely metrics, dimensions, time columns and identifiers per table."
    Input = NoArgs

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        semantic = {t.name: t.semantic for t in ctx.tables}
        return ToolResult(summary=render_schema(ctx.source), data={"semantic": semantic})


class ProfileInput(BaseModel):
    table: str | None = Field(None, description="Table name; optional when the source has one table")
    columns: list[str] = Field(default_factory=list, description="Columns to report; empty = table-level only")


class ProfileDataset(Tool):
    name = "profile_dataset"
    description = (
        "Instant, precomputed profile of a table (no query needed): row count, duplicated rows, and for the "
        "requested columns their non-null count, missing %, sum, mean, median, std, min, max (numbers), distinct "
        "count and top values (categories) or date range. Use it to answer whole-table statistics directly, and "
        "before analysis when data quality could affect conclusions."
    )
    Input = ProfileInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ProfileInput)
        table = ctx.table(args.table)
        profile = table.profile or {}
        sampled = bool(profile.get("sampled"))
        basis = f" (estimated from a {fmt_number(profile.get('sample_rows'))}-row sample)" if sampled else " (all rows)"
        findings = [
            FindingDraft(
                kind="stat",
                statement=f"Table {table.name} has {fmt_number(table.row_count)} rows, {table.column_count} columns, "
                f"{fmt_number(profile.get('duplicate_rows', 0))} fully duplicated rows and "
                f"{profile.get('missing_cells_pct', 0)}% missing cells",
                values={
                    "rows": table.row_count,
                    "columns": table.column_count,
                    "duplicate_rows": profile.get("duplicate_rows", 0),
                    "missing_cells_pct": profile.get("missing_cells_pct"),
                },
                entities=[table.name],
                payload={"source": "dataset profile", "sampled": sampled},
            )
        ]
        lines = [
            f"rows={fmt_number(table.row_count)} duplicates={profile.get('duplicate_rows', 0)} "
            f"missing_cells={profile.get('missing_cells_pct')}%{basis}"
        ]
        wanted = {c.lower() for c in args.columns}
        known = {c.name.lower(): c for c in table.columns} | {c.original_name.lower(): c for c in table.columns}
        missing = [c for c in args.columns if c.lower() not in known]
        if missing:
            from app.services.sql.validator import suggest

            options = sorted({o for name in missing for o in suggest(name, [c.name for c in table.columns])})
            raise ToolError(
                "unknown_column",
                f"Unknown column(s) {missing}." + (f" Did you mean: {', '.join(options)}?" if options else ""),
                {"column": missing[0], "suggestions": options, "available": [c.name for c in table.columns]},
            )
        selected = [known[c] for c in wanted] if wanted else []
        for column in selected:
            draft = _column_finding(table.name, table.row_count, column, basis, sampled)
            findings.append(draft)
            lines.append(draft.statement)
        for column in table.columns:
            stats = column.stats or {}
            if stats.get("outlier_count_iqr") and (not wanted or column in selected):
                lines.append(
                    f"{column.name}: {stats['outlier_count_iqr']} IQR outliers, bounds "
                    f"{stats.get('outlier_bounds')}, extreme values {stats.get('suspicious_values')}"
                )
        lines.extend(f"warning: {w}" for w in profile.get("warnings", []))
        return ToolResult(summary="\n".join(lines), data={"profile": profile}, findings=findings)


def _column_finding(table: str, rows: int, column: ColumnMetadata, basis: str, sampled: bool) -> FindingDraft:
    stats = column.stats or {}
    name = column.name
    common = {
        "non_null": stats.get("count"),
        "null_count": stats.get("null_count"),
        "missing_pct": stats.get("missing_pct"),
        "distinct": stats.get("distinct_count"),
    }
    payload = {"source": "dataset profile", "sampled": sampled, "column": name}
    if column.inferred_type in {"integer", "float"}:
        keys = ("sum", "mean", "median", "std", "min", "max", "q1", "q3")
        values = {**common, **{k: stats.get(k) for k in keys}}
        statement = (
            f"Column {name} in {table}{basis}: {fmt_number(stats.get('count'))} non-null of {fmt_number(rows)} rows "
            f"({stats.get('missing_pct', 0)}% missing); sum {fmt_number(stats.get('sum'))}, mean "
            f"{fmt_number(stats.get('mean'))}, median {fmt_number(stats.get('median'))}, std "
            f"{fmt_number(stats.get('std'))}, min {fmt_number(stats.get('min'))}, max {fmt_number(stats.get('max'))}"
        )
        formula = "mean = sum / non_null" if stats.get("count") else None
    elif column.inferred_type in {"date", "datetime"}:
        values = common
        statement = (
            f"Column {name} in {table}{basis}: dates from {stats.get('min')} to {stats.get('max')} "
            f"({fmt_number(stats.get('span_days'))} days, {stats.get('granularity')} grain), "
            f"{fmt_number(stats.get('count'))} non-null of {fmt_number(rows)} rows "
            f"({stats.get('missing_pct', 0)}% missing)"
        )
        formula = None
    else:
        top = (stats.get("top_values") or [])[:5]
        values = {**common, **{f"count_{t['value']}": t["count"] for t in top}}
        shown = (
            ""
            if column.is_pii
            else "; most frequent: " + ", ".join(f"{t['value']} ({fmt_number(t['count'])})" for t in top)
        )
        statement = (
            f"Column {name} in {table}{basis}: {fmt_number(stats.get('distinct_count'))} distinct values, "
            f"{fmt_number(stats.get('count'))} non-null of {fmt_number(rows)} rows "
            f"({stats.get('missing_pct', 0)}% missing){shown}"
        )
        formula = None
        if column.is_pii:
            values = common
    return FindingDraft(
        kind="stat",
        statement=statement,
        values={k: v for k, v in values.items() if v is not None},
        formula=formula,
        entities=[name] + ([str(t["value"]) for t in (stats.get("top_values") or [])[:5]] if not column.is_pii else []),
        payload=payload,
    )
