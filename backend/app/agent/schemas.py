"""Structured artifacts exchanged with the LLM. These are what get stored and shown; never free reasoning."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class PlanStep(BaseModel):
    id: str
    title: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    expected_output: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, value: Any) -> str:
        return str(value).strip().lower().lstrip("$") or "s"

    @field_validator("depends_on", mode="before")
    @classmethod
    def _deps(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(v).strip().lower().lstrip("$") for v in value]


class ContextUpdate(BaseModel):
    filters: list[dict[str, Any]] = Field(default_factory=list)
    metric: str | None = None
    dimension: str | None = None
    period: str | None = None


class Plan(BaseModel):
    goal: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    context_update: ContextUpdate = Field(default_factory=ContextUpdate)
    steps: list[PlanStep] = Field(default_factory=list)


class Repair(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class Revision(BaseModel):
    complete: bool = True
    reason: str = ""
    additional_steps: list[PlanStep] = Field(default_factory=list)


class DraftItem(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)
    section: str | None = None

    @field_validator("citations", mode="before")
    @classmethod
    def _cites(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [v for v in value.replace(",", " ").split() if v]
        return [str(v).strip("[] ") for v in value]


class Draft(BaseModel):
    headline: str = ""
    summary: list[DraftItem] = Field(default_factory=list)
    facts: list[DraftItem] = Field(default_factory=list)
    interpretations: list[DraftItem] = Field(default_factory=list)
    recommendations: list[DraftItem] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)

    @field_validator("summary", "facts", "interpretations", "recommendations", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [{"text": value}]
        if isinstance(value, list):
            return [{"text": v} if isinstance(v, str) else v for v in value]
        return value

    @field_validator("caveats", "follow_up_questions", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [v.get("text", str(v)) if isinstance(v, dict) else str(v) for v in value]
        return value


class RewriteItem(BaseModel):
    index: int
    text: str = ""
    citations: list[str] = Field(default_factory=list)


class Rewrite(BaseModel):
    items: list[RewriteItem] = Field(default_factory=list)
