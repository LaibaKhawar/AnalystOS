"""Final-answer drafting from findings (LLM), before deterministic verification."""

from __future__ import annotations

from app.agent.llm.base import LLMProvider
from app.agent.llm.structured import CallLog, generate_structured
from app.agent.prompts import REWRITE_SYSTEM, SYNTHESIS_SYSTEM
from app.agent.schemas import Draft, Rewrite
from app.db.models import Chart, Finding

_PRIORITY = {
    "comparison": 0,
    "driver": 0,
    "anomaly": 1,
    "ranking": 1,
    "correlation": 1,
    "stat": 2,
    "trend": 2,
    "value": 3,
}
MAX_FINDINGS_IN_PROMPT = 90


def select_findings(findings: list[Finding], limit: int = MAX_FINDINGS_IN_PROMPT) -> list[Finding]:
    if len(findings) <= limit:
        return findings
    ranked = sorted(enumerate(findings), key=lambda p: (_PRIORITY.get(p[1].kind, 4), p[0]))
    keep = {id(f) for _, f in ranked[:limit]}
    return [f for f in findings if id(f) in keep]


def render_findings(findings: list[Finding]) -> str:
    return "\n".join(f"{f.label} [{f.kind}]: {f.statement}" for f in findings)


def draft_answer(
    llm: LLMProvider,
    log: CallLog,
    *,
    question: str,
    goal: str,
    assumptions: list[str],
    findings: list[Finding],
    charts: list[Chart],
    failures: list[str],
    conversation: str,
) -> Draft:
    selected = select_findings(findings)
    chart_lines = "\n".join(f"- {c.title} ({c.chart_type})" for c in charts) or "none"
    failure_lines = "\n".join(f"- {f}" for f in failures) or "none"
    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question}\nANALYSIS GOAL: {goal}\nASSUMPTIONS: {assumptions or 'none'}\n"
                f"Conversation context:\n<data>\n{conversation or 'none'}\n</data>\n\n"
                "FINDINGS (the only allowed source of numbers):\n"
                f"<data>\n{render_findings(selected) or 'none'}\n</data>\n\n"
                f"CHARTS PRODUCED:\n{chart_lines}\n\nSTEPS THAT FAILED:\n{failure_lines}\n\nReturn the answer JSON."
            ),
        },
    ]
    return generate_structured(llm, messages, Draft, purpose="synthesize", log=log, max_tokens=2500)


def rewrite_unsupported(
    llm: LLMProvider, log: CallLog, *, sentences: list[tuple[str, list[str]]], findings: list[Finding]
) -> Rewrite:
    """One bounded attempt to repair sentences the verifier rejected. Output is re-verified by the caller."""
    listing = "\n".join(
        f"{i}. {text}  (numbers not found: {', '.join(bad)})" for i, (text, bad) in enumerate(sentences)
    )
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"FINDINGS:\n<data>\n{render_findings(select_findings(findings))}\n</data>\n\n"
                f"SENTENCES TO FIX:\n{listing}\n\nReturn the JSON."
            ),
        },
    ]
    return generate_structured(llm, messages, Rewrite, purpose="rewrite", log=log, max_tokens=1500)
