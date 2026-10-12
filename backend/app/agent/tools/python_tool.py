"""execute_python: run model-written pandas code inside the Docker sandbox (never in-process)."""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.context import ToolContext
from app.agent.tools.base import FindingDraft, Tool, ToolError, ToolResult
from app.agent.tools.common import compact_table, rows_findings
from app.core.config import get_settings
from app.db.models import PythonExecution
from app.services.sql.validator import suggest


class ExecutePythonInput(BaseModel):
    code: str = Field(..., description="pandas/numpy/scipy/sklearn code. Assign the final answer to `result`")
    tables: list[str] = Field(default_factory=list, description="Dataset tables to load as dfs['<table>']")
    results: list[str] = Field(default_factory=list, description="Earlier result_ids to load as dfs['<result_id>']")
    purpose: str = ""


class ExecutePython(Tool):
    name = "execute_python"
    description = ("Run Python in an isolated sandbox (no network, no files, 30s, 512MB). Tables are available as "
                   "dfs['name'] (and df when only one is loaded). Allowed: pandas, numpy, scipy, sklearn, "
                   "statsmodels, matplotlib (use save_chart(fig, title)). Assign the answer to `result` "
                   "(DataFrame, Series, dict or number).")
    Input = ExecutePythonInput

    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        assert isinstance(args, ExecutePythonInput)
        settings = get_settings()
        names = list(dict.fromkeys(args.tables)) or ([ctx.tables[0].name] if len(ctx.tables) == 1 and not args.results
                                                     else [])
        with tempfile.TemporaryDirectory(prefix="analystos-py-") as tmp:
            inputs: dict[str, Path] = {}
            known_columns: dict[str, list[str]] = {}
            for name in names:
                table = ctx.table(name)
                target = Path(tmp) / f"{table.name}.parquet"
                ctx.engine.export_table_parquet(table.name, str(target), max_rows=1_000_000)
                inputs[table.name] = target
                known_columns[table.name] = [c.name for c in table.columns]
            for ref in args.results:
                result_table = ctx.get_result_table(ref)
                target = Path(tmp) / f"{result_table.id}.parquet"
                _write_result_parquet(result_table.columns, result_table.rows, target)
                inputs[result_table.id] = target
                known_columns[result_table.id] = [c["name"] for c in result_table.columns]
            if not inputs:
                raise ToolError("invalid_arguments", "Pass at least one table or result to load",
                                {"available_tables": [t.name for t in ctx.tables]})
            outcome = ctx.sandbox.run(args.code, inputs, max_rows=settings.sql_max_rows)

        record = PythonExecution(
            analysis_id=ctx.analysis_id, tool_execution_id=ctx.current_execution_id, code=args.code,
            static_check=outcome.static_check.to_dict() if outcome.static_check else {}, status=outcome.status,
            exit_code=outcome.exit_code, stdout=outcome.stdout[-5000:], stderr=outcome.stderr[-5000:],
            limits=outcome.limits, duration_ms=outcome.duration_ms,
        )
        ctx.db.add(record)
        ctx.db.flush()
        artifacts = _store_artifacts(ctx, record.id, outcome.artifacts)
        record.artifacts = artifacts

        if outcome.status == "blocked":
            raise ToolError("static_check", f"Code rejected before execution: {outcome.error_message}")
        if outcome.status == "unavailable":
            raise ToolError("sandbox_unavailable", outcome.error_message or "Python sandbox unavailable")
        if outcome.status in {"timeout", "oom"}:
            raise ToolError("resource_limit", outcome.error_message or "Resource limit exceeded")
        if not outcome.ok:
            raise ToolError("python_error", _explain(outcome.error_type, outcome.error_message, outcome.line),
                            _hints(outcome.error_type, outcome.error_message, known_columns))

        payload = outcome.result or {}
        source = {"type": "python", "python_execution_id": record.id}
        if payload.get("type") == "table":
            cols = payload["columns"]
            rows = payload["rows"]
            table = ctx.save_result_table(args.purpose or "Python result", cols, rows,
                                          truncated=bool(payload.get("truncated")), source=source)
            names = [c["name"] for c in cols]
            return ToolResult(
                summary=f"result_id={table.id} rows={payload.get('row_count')}\n{compact_table(names, rows)}"
                        + (f"\ncharts saved: {len(artifacts)}" if artifacts else ""),
                data={"row_count": payload.get("row_count"), "artifacts": artifacts},
                result_table_id=table.id, findings=rows_findings(args.purpose or "Python result", names, rows),
            )
        findings = _scalar_findings(args.purpose or "Python result", payload)
        table = ctx.save_result_table(args.purpose or "Python result",
                                      [{"name": "key", "type": "str"}, {"name": "value", "type": "any"}],
                                      _flatten(payload), source=source)
        return ToolResult(summary=f"result_id={table.id} value={str(payload.get('value'))[:1500]}",
                          data={"result": payload, "artifacts": artifacts}, result_table_id=table.id,
                          findings=findings)


def _write_result_parquet(columns: list[dict[str, Any]], rows: list[list[Any]], target: Path) -> None:
    import pandas as pd

    pd.DataFrame(rows, columns=[c["name"] for c in columns]).to_parquet(target)


def _store_artifacts(ctx: ToolContext, record_id: str, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stored = []
    base = get_settings().artifacts_dir / ctx.analysis_id / record_id
    for artifact in artifacts:
        base.mkdir(parents=True, exist_ok=True)
        path = base / artifact["file"]
        path.write_bytes(artifact["data"])
        stored.append({"file": artifact["file"], "title": artifact.get("title"), "path": str(path),
                       "sha256": hashlib.sha256(artifact["data"]).hexdigest()})
    return stored


def _explain(error_type: str | None, message: str | None, line: int | None) -> str:
    where = f" (line {line})" if line else ""
    return f"{error_type or 'Error'}{where}: {(message or '').strip()[:600]}"


def _hints(error_type: str | None, message: str | None, known: dict[str, list[str]]) -> dict[str, Any]:
    hints: dict[str, Any] = {"columns": {k: v[:60] for k, v in known.items()}}
    if error_type == "KeyError" and message:
        missing = re.sub(r"^[\"'\[]+|[\"'\]]+$", "", message.strip())
        all_columns = sorted({c for cols in known.values() for c in cols})
        options = suggest(missing, all_columns)
        hints["missing_key"] = missing
        if options:
            hints["suggestions"] = options
    return hints


def _flatten(payload: dict[str, Any]) -> list[list[Any]]:
    value = payload.get("value")
    if isinstance(value, dict):
        return [[str(k), v if not isinstance(v, dict | list) else str(v)[:500]] for k, v in value.items()]
    if isinstance(value, list):
        return [[str(i), v if not isinstance(v, dict | list) else str(v)[:500]] for i, v in enumerate(value)]
    return [["result", value]]


def _scalar_findings(name: str, payload: dict[str, Any]) -> list[FindingDraft]:
    value = payload.get("value")
    findings = []
    if isinstance(value, dict):
        for key, item in list(value.items())[:30]:
            if isinstance(item, int | float) and not isinstance(item, bool):
                findings.append(FindingDraft(kind="value", statement=f"{name}: {key} = {item}",
                                             values={"value": item}, entities=[str(key)]))
    elif isinstance(value, int | float) and not isinstance(value, bool):
        findings.append(FindingDraft(kind="value", statement=f"{name} = {value}", values={"value": value}))
    return findings
