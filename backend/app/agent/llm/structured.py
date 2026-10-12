"""Structured (JSON) generation with schema validation and a bounded repair loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.agent.llm.base import LLMProvider, LLMResponse, Usage
from app.core.errors import LLMError

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            snippet = candidate[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                cleaned = re.sub(r",\s*([}\]])", r"\1", snippet)  # trailing commas
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
    raise ValueError("No valid JSON object found in the model output")


@dataclass
class CallLog:
    """Per-analysis LLM accounting (tokens, calls, latency)."""

    usage: Usage = field(default_factory=Usage)
    calls: int = 0
    latency_ms: int = 0
    model: str | None = None
    by_purpose: dict[str, int] = field(default_factory=dict)

    def record(self, response: LLMResponse, purpose: str) -> None:
        self.usage = self.usage + response.usage
        self.calls += 1
        self.latency_ms += response.latency_ms
        self.model = response.model
        self.by_purpose[purpose] = self.by_purpose.get(purpose, 0) + 1


def generate_structured(
    llm: LLMProvider,
    messages: list[dict[str, Any]],
    schema: type[T],
    *,
    purpose: str,
    log: CallLog,
    max_repairs: int = 2,
    max_tokens: int | None = None,
) -> T:
    conversation = list(messages)
    last_error = ""
    for attempt in range(max_repairs + 1):
        response = llm.complete(
            conversation,
            purpose=purpose if attempt == 0 else f"{purpose}_repair",
            json_mode=True,
            max_tokens=max_tokens,
        )
        log.record(response, purpose)
        try:
            data = extract_json(response.content)
            return schema.model_validate(data)
        except (ValueError, ValidationError) as exc:
            last_error = _summarise_error(exc)
            conversation = [
                *list(messages),
                {"role": "assistant", "content": response.content[:4000]},
                {
                    "role": "user",
                    "content": "Your previous reply was not valid for the required JSON schema. "
                    f"Problems: {last_error}\nReturn ONLY the corrected JSON object, no prose.",
                },
            ]
    raise LLMError(f"The model did not return valid structured output for {purpose}: {last_error[:300]}")


def _summarise_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors()[:6]:
            loc = ".".join(str(x) for x in err.get("loc", ()))
            parts.append(f"{loc}: {err.get('msg')}")
        return "; ".join(parts)
    return str(exc)[:300]
