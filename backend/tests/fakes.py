"""Test double for the LLM provider. Lives in tests only; production code never uses it."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from app.agent.llm.base import LLMProvider, LLMResponse, Usage

Responder = Callable[[list[dict[str, Any]]], Any]


class ScriptedLLM(LLMProvider):
    """Returns pre-scripted JSON per purpose ("plan", "repair", "revise", "synthesize", "rewrite").

    A script entry may be a dict (serialised to JSON), a raw string, or a callable receiving the messages
    (useful to build answers from the findings the agent actually produced).
    """

    def __init__(self, scripts: dict[str, list[Any]] | None = None, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self.scripts: dict[str, deque[Any]] = defaultdict(deque)
        for purpose, items in (scripts or {}).items():
            self.scripts[purpose].extend(items)
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append((purpose, messages))
        base = purpose.removesuffix("_repair")
        queue = self.scripts.get(base)
        if not queue:
            default = {
                "revise": {"complete": True, "reason": "done", "additional_steps": []},
                "rewrite": {"items": []},
            }.get(base)
            if default is None:
                raise AssertionError(
                    f"No scripted response left for purpose '{purpose}': {messages[-1]['content'][-600:]}"
                )
            item: Any = default
        else:
            item = queue.popleft()
        if callable(item):
            item = item(messages)
        content = item if isinstance(item, str) else json.dumps(item)
        return LLMResponse(content=content, model=self.model, usage=Usage(1000, 200), latency_ms=5)

    def purposes(self) -> list[str]:
        return [p for p, _ in self.calls]


def findings_in(messages: list[dict[str, Any]]) -> dict[str, str]:
    """Parse 'F1 [kind]: statement' lines from a synthesis prompt."""
    text = messages[-1]["content"]
    out = {}
    for line in text.splitlines():
        if line.startswith("F") and "]: " in line:
            label = line.split(" ", 1)[0]
            out[label] = line.split("]: ", 1)[1]
    return out
