"""Backend for deterministic browser tests (`npm run e2e:ci`).

Starts the real API with analyses run inline and the LLM replaced by a rule-based stand-in that reads the column
guide in the planner prompt and the findings in the synthesis prompt. Everything else (ingestion, tools, SQL
validation, verification, charts, reports) is the production code path. Lives under tests/ and is never shipped.

Usage: python -m tests.e2e_server   (env: E2E_DATABASE_URL, E2E_PORT=8001)
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from typing import Any

from cryptography.fernet import Fernet

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("E2E_DATABASE_URL", "postgresql+psycopg://analystos:analystos@localhost:5434/analystos_e2e"),
)
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="analystos-e2e-"))
os.environ["RUN_ANALYSES_INLINE"] = "true"
os.environ["EMBEDDING_BASE_URL"] = ""
os.environ["LOGIN_RATE_PER_MINUTE"] = "0"
os.environ["QUESTIONS_PER_HOUR"] = "0"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5174")

from app.agent.llm.base import LLMProvider, LLMResponse, Usage


class RuleBasedLLM(LLMProvider):
    """Deterministic stand-in: aggregate the first metric by the first dimension, chart it, cite the top result."""

    model = "e2e-rule-based"

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        prompt = messages[-1]["content"]
        base = purpose.removesuffix("_repair")
        if base == "plan":
            content = self._plan(prompt)
        elif base == "synthesize":
            content = self._answer(prompt)
        elif base == "revise":
            content = {"complete": True, "reason": "done", "additional_steps": []}
        elif base == "rewrite":
            content = {"items": []}
        else:
            content = {"tool": "list_tables", "args": {}, "reason": "fallback"}
        return LLMResponse(content=json.dumps(content), model=self.model, usage=Usage(500, 120), latency_ms=5)

    @staticmethod
    def _names(prompt: str, label: str) -> list[str]:
        match = re.search(rf"{label}=\[([^\]]*)\]", prompt)
        return re.findall(r"'([^']+)'", match.group(1)) if match else []

    def _plan(self, prompt: str) -> dict[str, Any]:
        metrics, dims = self._names(prompt, "metrics"), self._names(prompt, "dimensions")
        metric = "revenue" if "revenue" in metrics else (metrics[0] if metrics else None)
        dim = "region" if "region" in dims else (dims[0] if dims else None)
        if not metric or not dim:
            return {"goal": "Inspect the data", "steps": [{"id": "s1", "title": "List tables", "tool": "list_tables"}]}
        return {
            "goal": f"Compare {metric} across {dim}",
            "steps": [
                {
                    "id": "s1",
                    "title": f"Total {metric} by {dim}",
                    "tool": "aggregate_metric",
                    "args": {"metric": {"column": metric, "agg": "sum"}, "group_by": [dim]},
                },
                {
                    "id": "s2",
                    "title": f"Chart {metric} by {dim}",
                    "tool": "create_chart",
                    "depends_on": ["s1"],
                    "args": {
                        "result_id": "$s1",
                        "chart_type": "bar",
                        "x": dim,
                        "y": [metric],
                        "title": f"Total {metric} by {dim}",
                    },
                },
            ],
        }

    @staticmethod
    def _answer(prompt: str) -> dict[str, Any]:
        findings = {m.group(1): m.group(2) for m in re.finditer(r"^(F\d+) \[[a-z]+\]: (.+)$", prompt, re.M)}
        top = next(((label, text) for label, text in findings.items() if text.startswith("Highest")), None)
        if top is None:
            return {"headline": "Analysis complete", "summary": [], "facts": []}
        label, text = top
        return {
            "headline": text,
            "summary": [{"text": text, "citations": [label]}],
            "facts": [
                {"text": t, "citations": [lbl], "section": "segment"}
                for lbl, t in list(findings.items())[:3]
                if lbl != label
            ],
            "recommendations": [{"text": "Review the lowest-ranked segment with its owner.", "citations": []}],
            "follow_up_questions": ["How did this change over time?"],
        }


def main() -> None:
    import uvicorn
    from sqlalchemy import text

    import app.db.models
    from app.db.base import Base
    from app.db.session import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    import app.workers.tasks as tasks

    tasks.get_provider = RuleBasedLLM  # type: ignore[assignment]
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8001")), log_level="warning")


if __name__ == "__main__":
    main()
