"""LLM provider abstraction. The agent depends only on this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Usage
    latency_ms: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None


class LLMProvider(ABC):
    model: str

    @abstractmethod
    def complete(
        self, messages: list[dict[str, Any]], *, purpose: str, json_mode: bool = False, temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Optional: return embeddings or None if the provider has no embedding endpoint configured."""
        return None
