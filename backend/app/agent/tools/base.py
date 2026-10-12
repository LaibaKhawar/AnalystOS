"""Tool framework: typed inputs/outputs, validation, error classification, execution logging.

Each tool declares a pydantic input model. Execution goes through `ToolRunner`, which validates input,
times the call, persists a ToolExecution row, records metrics, and converts failures into a structured,
sanitized error the agent can use to fix its next attempt.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.core.errors import AnalystError
from app.core.logging import get_logger
from app.core.metrics import TOOL_CALLS, TOOL_LATENCY
from app.db.models import ToolExecution

if TYPE_CHECKING:
    from app.agent.context import ToolContext

log = get_logger(__name__)

# Errors the agent can plausibly fix by changing its arguments.
RECOVERABLE_KINDS = {
    "invalid_arguments",
    "unknown_column",
    "unknown_table",
    "syntax",
    "type_error",
    "execution_error",
    "python_error",
    "missing_result",
    "empty_result",
    "unknown_result",
    "bad_period",
    "invalid_chart",
    "statement_type",
    "forbidden_operation",
    "forbidden_function",
    "restricted_column",
    "static_check",
}


@dataclass
class FindingDraft:
    kind: str
    statement: str
    values: dict[str, Any]
    formula: str | None = None
    entities: list[str] = field(default_factory=list)
    periods: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    summary: str  # compact, LLM-facing observation (no raw bulk data)
    data: dict[str, Any] = field(default_factory=dict)
    result_table_id: str | None = None
    findings: list[FindingDraft] = field(default_factory=list)
    chart_ids: list[str] = field(default_factory=list)
    notable: bool = False  # signals the planner that revision may be warranted


@dataclass
class ToolError(Exception):
    kind: str
    message: str
    hints: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    @property
    def recoverable(self) -> bool:
        return self.kind in RECOVERABLE_KINDS


@dataclass
class ToolOutcome:
    tool: str
    execution_id: str
    ok: bool
    result: ToolResult | None
    error: ToolError | None
    duration_ms: int
    finding_labels: list[str] = field(default_factory=list)


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Input: ClassVar[type[BaseModel]]
    planner_visible: ClassVar[bool] = True

    @abstractmethod
    def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult: ...

    @classmethod
    def schema_hint(cls) -> dict[str, Any]:
        """Compact argument description for prompts (smaller than full JSON schema)."""
        schema = cls.Input.model_json_schema()
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        defs = schema.get("$defs", {})
        out: dict[str, Any] = {}
        for name, prop in props.items():
            out[name + ("" if name in required else "?")] = _describe(prop, defs)
        return out


def _describe(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in prop:
        ref = defs.get(prop["$ref"].split("/")[-1], {})
        inner = {k: _describe(v, defs) for k, v in ref.get("properties", {}).items()}
        return "{" + ", ".join(f"{k}: {v}" for k, v in inner.items()) + "}"
    if "anyOf" in prop:
        options = [_describe(p, defs) for p in prop["anyOf"] if p.get("type") != "null"]
        text = " | ".join(options) if options else "any"
    elif "enum" in prop:
        text = " | ".join(repr(v) for v in prop["enum"])
    elif prop.get("type") == "array":
        text = f"list[{_describe(prop.get('items', {}), defs)}]"
    else:
        text = str(prop.get("type", "any"))
    if prop.get("description"):
        text += f"  # {prop['description']}"
    return text


class ToolRunner:
    def __init__(self, ctx: ToolContext, tools: dict[str, Tool]) -> None:
        self.ctx = ctx
        self.tools = tools

    def execute(
        self,
        tool_name: str,
        raw_args: dict[str, Any],
        *,
        step_id: str | None = None,
        attempt: int = 1,
        retry_of: str | None = None,
        retry_reason: str | None = None,
    ) -> ToolOutcome:
        ctx = self.ctx
        record = ToolExecution(
            analysis_id=ctx.analysis_id,
            step_id=step_id,
            tool=tool_name,
            input=_jsonable(raw_args),
            status="error",
            attempt=attempt,
            retry_of_id=retry_of,
            retry_reason=retry_reason,
        )
        ctx.db.add(record)
        ctx.db.flush()
        ctx.current_execution_id = record.id
        started = time.perf_counter()
        tool = self.tools.get(tool_name)
        result: ToolResult | None = None
        error: ToolError | None = None
        try:
            if tool is None:
                raise ToolError("unknown_tool", f"Unknown tool '{tool_name}'. Available: {', '.join(self.tools)}")
            try:
                args = tool.Input.model_validate(raw_args or {})
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(x) for x in e['loc']) or 'args'}: {e['msg']}" for e in exc.errors()[:6]
                )
                raise ToolError(
                    "invalid_arguments",
                    f"Invalid arguments for {tool_name}: {problems}",
                    {"expected": tool.schema_hint()},
                ) from exc
            result = tool.run(ctx, args)
        except ToolError as exc:
            error = exc
        except AnalystError as exc:
            kind = str(exc.details.get("kind") or exc.code)
            hints = {k: v for k, v in exc.details.items() if k != "kind"}
            error = ToolError(
                kind if kind in RECOVERABLE_KINDS else "invalid_arguments" if exc.code == "validation_failed" else kind,
                exc.message,
                hints,
            )
        except Exception as exc:  # unexpected bug: never leak internals to the model
            log.error("tool_crashed", tool=tool_name, error=repr(exc), trace=traceback.format_exc()[-2000:])
            error = ToolError("internal_error", f"The {tool_name} tool failed unexpectedly ({exc.__class__.__name__})")

        duration = int((time.perf_counter() - started) * 1000)
        record.duration_ms = duration
        labels: list[str] = []
        if error is None and result is not None:
            record.status = "success"
            labels = ctx.store_findings(result.findings, record.id, result.result_table_id)
            record.output = _jsonable(
                {
                    "summary": result.summary,
                    "result_table_id": result.result_table_id,
                    "findings": labels,
                    "chart_ids": result.chart_ids,
                    "data": result.data,
                }
            )
        else:
            assert error is not None
            record.error, record.error_kind = error.message[:2000], error.kind
            record.output = _jsonable({"hints": error.hints})
        ctx.db.flush()
        status = "success" if error is None else "error"
        TOOL_CALLS.labels(tool=tool_name, status=status).inc()
        TOOL_LATENCY.labels(tool=tool_name, status=status).observe(duration / 1000)
        log.info(
            "tool_executed",
            tool=tool_name,
            status=status,
            duration_ms=duration,
            attempt=attempt,
            error_kind=error.kind if error else None,
        )
        return ToolOutcome(tool_name, record.id, error is None, result, error, duration, labels)


def _jsonable(value: Any) -> Any:
    from app.services.datasources.base import to_jsonable

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return to_jsonable(value)
