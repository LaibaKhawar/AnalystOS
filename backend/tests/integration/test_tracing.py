from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.integration.test_analysis_flows import COMPARE, cite_findings


def test_analysis_produces_a_span_tree(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)  # installed by the app at startup
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    source = upload(data_dir / "sales.csv")
    agent.script(
        plan=[
            {
                "goal": "q",
                "steps": [
                    {
                        "id": "s1",
                        "title": "Compare",
                        "tool": "compare_periods",
                        "args": {**COMPARE, "dimension": "region"},
                    }
                ],
            }
        ],
        synthesize=[cite_findings(lambda t: "Lahore" in t, 1)],
    )
    analysis = ask(source["id"], "How did regions change in Q3 2026 versus Q2?")
    spans = {s.name: s for s in exporter.get_finished_spans()}
    root = spans["analysis"]
    assert root.attributes["analysis.id"] == analysis["id"]
    assert root.attributes["analysis.status"] == "completed"
    tool = spans["tool.compare_periods"]
    assert tool.parent.span_id == root.context.span_id and tool.attributes["tool.status"] == "success"
    sql = spans["sql.execute"]
    assert sql.parent.span_id == tool.context.span_id and sql.attributes["sql.status"] == "success"
    assert {"plan", "tool.compare_periods", "sql.execute"} <= set(spans)
