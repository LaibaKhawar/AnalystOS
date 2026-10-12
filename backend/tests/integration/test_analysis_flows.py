"""End-to-end API flows with the real orchestrator, tools, verifier and sandbox; only the LLM is scripted."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import AnalysisMemory, PythonExecution, SQLExecution, ToolExecution
from tests.conftest import docker_available
from tests.fakes import findings_in

COMPARE = {"metric": {"column": "revenue", "agg": "sum"}, "current_period": "2026-Q3", "previous_period": "2026-Q2"}


def cite_findings(predicate: Callable[[str], bool], limit: int = 3) -> Callable[[list[dict[str, Any]]], dict[str, Any]]:
    """Synthesis double: restates real finding statements (with citations) as facts."""

    def build(messages: list[dict[str, Any]]) -> dict[str, Any]:
        found = [(label, text) for label, text in findings_in(messages).items() if predicate(text)][:limit]
        assert found, "expected findings in the synthesis prompt"
        return {
            "headline": found[0][1],
            "summary": [{"text": found[0][1], "citations": [found[0][0]]}],
            "facts": [{"text": text, "citations": [label], "section": "driver"} for label, text in found[1:]],
            "interpretations": [{"text": "The Lahore decline was driven by weaker laptop demand.", "citations": []}],
            "recommendations": [{"text": "Review laptop pricing and stock in Lahore stores.", "citations": []}],
            "caveats": ["Data ends on 2026-09-30."],
            "follow_up_questions": ["Was the Lahore decline visible before July?"],
        }

    return build


def test_full_flow_compare_drivers_chart_report(client: TestClient, auth: dict[str, str], agent, upload, ask,  # type: ignore[no-untyped-def]
                                                data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    assert source["status"] == "ready" and source["table_count"] == 1
    tables = client.get(f"/api/sources/{source['id']}/tables", headers=auth).json()
    assert tables[0]["profile"]["duplicate_rows"] == 40
    agent.script(
        plan=[{"goal": "Explain the Q3 decline", "steps": [
            {"id": "s1", "title": "Compare quarters by region", "tool": "compare_periods",
             "args": {**COMPARE, "dimension": "region"}},
            {"id": "s2", "title": "Find drivers", "tool": "identify_drivers",
             "args": {**COMPARE, "dimensions": ["region", "product"], "quantity_column": "units"}},
            {"id": "s3", "title": "Chart regional change", "tool": "create_chart",
             "args": {"result_id": "$s1", "chart_type": "bar", "x": "region", "y": ["previous", "current"],
                      "title": "Revenue by region, Q2 vs Q3 2026"}},
        ]}],
        synthesize=[cite_findings(lambda t: "Lahore" in t or "2026-Q2 =" in t)],
    )
    analysis = ask(source["id"], "Why did revenue decline in Q3 2026?")
    assert analysis["status"] == "completed", analysis["error"]
    assert [s["status"] for s in analysis["steps"]] == ["done", "done", "done"]
    verification = analysis["answer"]["verification"]
    assert verification["verified"] >= 2 and verification["final_unsupported_rate"] == 0.0
    assert verification["charts_verified"] == verification["charts_total"] == 1

    claims = client.get(f"/api/analyses/{analysis['id']}/claims", headers=auth).json()
    facts = [c for c in claims if c["kind"] == "fact"]
    assert facts and all(c["status"] == "verified" and c["evidence"] for c in facts)
    hypothesis = next(c for c in claims if c["text"].startswith("Hypothesis"))
    assert hypothesis["kind"] == "interpretation"

    evidence = client.get(f"/api/analyses/{analysis['id']}/claims/{facts[0]['id']}/evidence", headers=auth).json()
    item = evidence["evidence"][0]
    assert item["sql"] and "SELECT" in item["sql"][0]["sql"].upper()
    assert item["result"]["rows"] and item["formula"]

    chart = client.get(f"/api/analyses/{analysis['id']}/charts", headers=auth).json()[0]
    assert chart["verified"] and chart["spec"]["y_zero"] is True
    regions = {row["region"] for row in chart["data"]}
    assert regions == {"Lahore", "Karachi", "Islamabad", "Faisalabad", "Multan"}

    report = client.post(f"/api/analyses/{analysis['id']}/report", headers=auth)
    assert report.status_code == 201
    html = client.get(f"/api/reports/{report.json()['id']}/html", headers=auth).text
    for section in ("Executive summary", "Dataset overview", "Interpretations", "Recommendations",
                    "Risks and caveats", "Evidence appendix"):
        assert section in html
    assert "Lahore" in html and "SELECT" in html
    xlsx = client.get(f"/api/reports/{report.json()['id']}/results.xlsx", headers=auth)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"

    events = client.get(f"/api/analyses/{analysis['id']}/events", headers=auth).json()
    types = [e["type"] for e in events]
    assert types[0] == "status" and "plan" in types and types[-1] == "completed"
    assert all("think" not in e["message"].lower() for e in events)
    assert db.query(SQLExecution).filter(SQLExecution.analysis_id == analysis["id"]).count() >= 3
    assert db.query(AnalysisMemory).filter(AnalysisMemory.analysis_id == analysis["id"]).count() == 1
    assert analysis["cost_usd"] > 0 and analysis["llm_calls"] >= 2  # scripted model is priced as gpt-4o-mini


def test_unknown_column_auto_corrected_without_llm(client: TestClient, auth, agent, upload, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    llm = agent.script(
        plan=[{"goal": "Revenue by region", "steps": [
            {"id": "s1", "title": "Revenue by regions", "tool": "aggregate_metric",
             "args": {"table": "orders", "metric": {"column": "revenue"}, "group_by": ["regions"]}}]}],
        synthesize=[cite_findings(lambda t: "Highest" in t, 1)],
    )
    analysis = ask(source["id"], "Show total revenue by regions")
    assert analysis["status"] == "completed"
    executions = db.query(ToolExecution).filter(ToolExecution.analysis_id == analysis["id"]).order_by(
        ToolExecution.created_at).all()
    assert [(e.status, e.attempt) for e in executions[:3]] == [("error", 1), ("error", 2), ("success", 3)]
    assert "auto-corrected" in (executions[2].retry_reason or "")
    assert "repair" not in llm.purposes()
    assert analysis["answer"]["tool_stats"]["recovered_retries"] >= 1


@pytest.mark.skipif(not docker_available(), reason="Docker sandbox image not available")
def test_python_key_error_recovered_by_llm_repair(client: TestClient, auth, agent, upload, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    bad = "result = df.groupby('regions')['revenue'].sum().sort_values(ascending=False).head(3)"
    good = "result = df.groupby('region')['revenue'].sum().sort_values(ascending=False).head(3)"
    llm = agent.script(
        plan=[{"goal": "Top regions", "steps": [
            {"id": "s1", "title": "Top regions in pandas", "tool": "execute_python",
             "args": {"code": bad, "tables": ["sales"], "purpose": "top regions"}}]}],
        repair=[lambda messages: {"tool": "execute_python", "reason": "column is region",
                                  "args": {"code": good, "tables": ["sales"], "purpose": "top regions"}}],
        synthesize=[cite_findings(lambda t: "region=Karachi" in t, 1)],
    )
    analysis = ask(source["id"], "Which regions earn the most? Use pandas.")
    assert analysis["status"] == "completed", analysis["error"]
    repair_prompt = next(m for p, m in llm.calls if p == "repair")[-1]["content"]
    assert "KeyError" in repair_prompt and "region" in repair_prompt  # sanitized error + schema hints
    runs = db.query(PythonExecution).filter(PythonExecution.analysis_id == analysis["id"]).order_by(
        PythonExecution.created_at).all()
    assert [r.status for r in runs] == ["error", "success"]
    executions = db.query(ToolExecution).filter(ToolExecution.analysis_id == analysis["id"],
                                                ToolExecution.tool == "execute_python").order_by(
        ToolExecution.created_at).all()
    assert executions[1].retry_of_id == executions[0].id and "KeyError" in executions[1].retry_reason


def test_repeated_identical_repair_does_not_loop(client: TestClient, auth, agent, upload, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    bad_sql = "SELECT zone, SUM(revenue) FROM sales GROUP BY zone"
    agent.script(
        plan=[{"goal": "x", "steps": [{"id": "s1", "title": "Bad query", "tool": "execute_sql",
                                       "args": {"sql": bad_sql}}]}],
        repair=[{"tool": "execute_sql", "args": {"sql": bad_sql}, "reason": "same"}] * 5,
        synthesize=[{"headline": "No result", "summary": [], "facts": [], "caveats": ["The query failed."]}],
    )
    analysis = ask(source["id"], "Revenue by zone")
    assert analysis["status"] == "completed"
    attempts = db.query(ToolExecution).filter(ToolExecution.analysis_id == analysis["id"]).count()
    assert attempts == 1  # identical repaired call is detected, no retry storm
    assert analysis["steps"][0]["status"] == "failed"


def test_destructive_sql_is_blocked_and_data_untouched(client: TestClient, auth, agent, upload, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    agent.script(
        plan=[{"goal": "Delete every table", "steps": [
            {"id": "s1", "title": "Delete data", "tool": "execute_sql", "args": {"sql": "DELETE FROM sales"}}]}],
        repair=[{"tool": "execute_sql", "args": {"sql": "DROP TABLE sales"}, "reason": "try drop"},
                {"tool": "execute_sql", "args": {"sql": "SELECT 1; DROP TABLE sales"}, "reason": "try again"},
                {"tool": "execute_sql", "args": {"sql": "WITH d AS (DELETE FROM sales RETURNING *) SELECT * FROM d"},
                 "reason": "cte"}],
        synthesize=[{"headline": "I cannot delete data", "summary": [{"text": "AnalystOS only runs read-only queries."}],
                     "caveats": ["Deletion requests are rejected."]}],
    )
    analysis = ask(source["id"], "Delete every table.")
    statuses = [s.status for s in db.query(SQLExecution).filter(SQLExecution.analysis_id == analysis["id"])]
    assert statuses and set(statuses) == {"blocked"}
    preview = client.get(f"/api/sources/{source['id']}/tables", headers=auth).json()[0]
    rows = client.get(f"/api/sources/{source['id']}/tables/{preview['id']}/preview", headers=auth).json()["rows"]
    assert len(rows) == 50


def test_clarification_request(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    agent.script(plan=[{"goal": "unclear", "needs_clarification": True,
                        "clarification_question": "Which metric do you mean by performance: revenue or units?",
                        "steps": []}])
    analysis = ask(source["id"], "How did it do?")
    assert analysis["status"] == "needs_clarification"
    messages = client.get(f"/api/conversations/{analysis['conversation_id']}/messages", headers=auth).json()
    assert messages[-1]["role"] == "assistant" and "revenue or units" in messages[-1]["content"]


def test_follow_up_keeps_context(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    lahore = [{"column": "region", "op": "=", "value": "Lahore"}]
    agent.script(
        plan=[
            {"goal": "Lahore Q3 vs Q2", "context_update": {"filters": lahore, "metric": "revenue", "period": "2026-Q3"},
             "steps": [{"id": "s1", "title": "Compare", "tool": "compare_periods", "args": {**COMPARE, "filters": lahore}}]},
            {"goal": "Enterprise only", "context_update": {"filters": lahore + [
                {"column": "customer_segment", "op": "=", "value": "Enterprise"}]},
             "steps": [{"id": "s1", "title": "Monthly", "tool": "aggregate_metric",
                        "args": {"metric": {"column": "revenue"}, "time_grain": "month", "period": "2026",
                                 "filters": lahore + [{"column": "customer_segment", "op": "=", "value": "Enterprise"}]}}]},
        ],
        synthesize=[cite_findings(lambda t: "region = Lahore" in t, 1),
                    cite_findings(lambda t: "Enterprise" in t, 2)],
    )
    first = ask(source["id"], "Why did Lahore decline?")
    assert first["status"] == "completed"
    second = ask(source["id"], "Show only enterprise customers, monthly.", conversation_id=first["conversation_id"])
    assert second["status"] == "completed"
    plan_prompt = [m for p, m in agent.llm.calls if p == "plan"][1][-1]["content"]
    assert "Lahore" in plan_prompt and "Active filters" in plan_prompt and "Why did Lahore decline?" in plan_prompt
    conversation = client.get(f"/api/conversations/{first['conversation_id']}", headers=auth).json()
    assert {f["column"] for f in conversation["state"]["filters"]} == {"region", "customer_segment"}
    assert len(conversation["state"]["history"]) == 2


def test_prompt_injection_cells_stay_data(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "adversarial_accounts.csv")
    tables = client.get(f"/api/sources/{source['id']}/tables", headers=auth).json()
    columns = {c["original_name"]: c for c in tables[0]["columns"]}
    assert {"Revenue ($)", "Customer ID", "2026 Sales", "Growth %"} <= set(columns)
    assert columns["Revenue ($)"]["name"] == "revenue_usd" and columns["Growth %"]["inferred_type"] in {"integer", "float"}
    assert "possible_prompt_injection" in columns["Notes"]["stats"]["flags"]
    agent.script(
        plan=[{"goal": "Revenue by region", "steps": [
            {"id": "s1", "title": "Revenue by region", "tool": "aggregate_metric",
             "args": {"metric": {"column": "revenue_usd"}, "group_by": ["sales_region"]}}]}],
        synthesize=[cite_findings(lambda t: "Highest" in t, 1)],
    )
    analysis = ask(source["id"], "Summarize revenue by sales region")
    assert analysis["status"] == "completed"
    system_prompt = agent.llm.calls[0][1][0]["content"]
    user_prompt = agent.llm.calls[0][1][-1]["content"]
    assert "untrusted DATA" in system_prompt
    data_block = user_prompt.split("<data>")[1].split("</data>")[0]
    assert "instruction-like text" in data_block  # flagged inside the fenced data block
    assert "SECRET_KEY" not in str(analysis) and "ENCRYPTION_KEY" not in str(analysis)


def test_hallucinated_numbers_removed_then_repaired(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")

    def rewrite(messages: list[dict[str, Any]]) -> dict[str, Any]:
        label, text = next((lbl, t) for lbl, t in findings_in(messages).items() if "Highest" in t)
        return {"items": [{"index": 0, "text": text, "citations": [label]}]}

    agent.script(
        plan=[{"goal": "Top region", "steps": [
            {"id": "s1", "title": "Revenue by region", "tool": "aggregate_metric",
             "args": {"metric": {"column": "revenue"}, "group_by": ["region"]}}]}],
        synthesize=[{"headline": "Karachi leads", "summary": [{"text": "Karachi generated 9,999,999.99 in revenue.",
                                                             "citations": ["F1"]}]}],
        rewrite=[rewrite],
    )
    analysis = ask(source["id"], "Which region produced the most revenue?")
    verification = analysis["answer"]["verification"]
    assert verification["removed"] == 1 and verification["repaired"] == 1
    assert verification["draft_unsupported_rate"] == 1.0 and verification["final_unsupported_rate"] == 0.0
    claims = client.get(f"/api/analyses/{analysis['id']}/claims", headers=auth).json()
    assert all("9,999,999.99" not in c["text"] for c in claims)
    removed = client.get(f"/api/analyses/{analysis['id']}/claims?include_removed=true", headers=auth).json()
    assert any(c["status"] == "removed" and "9,999,999.99" in c["text"] for c in removed)


def test_anomaly_root_cause_chart_report(client: TestClient, auth, agent, upload, ask, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    agent.script(
        plan=[{"goal": "Find August anomalies in Karachi", "steps": [
            {"id": "s1", "title": "Detect anomalies", "tool": "detect_anomalies",
             "args": {"metric": {"column": "revenue"}, "time_grain": "day", "period": "2026-06-01..2026-09-30",
                      "filters": [{"column": "region", "op": "=", "value": "Karachi"}], "threshold": 3.5}},
            {"id": "s2", "title": "Drivers", "tool": "identify_drivers",
             "args": {**COMPARE, "filters": [{"column": "region", "op": "=", "value": "Karachi"}],
                      "dimensions": ["store", "product"]}},
            {"id": "s3", "title": "Chart", "tool": "create_chart",
             "args": {"result_id": "$s1", "chart_type": "line", "x": "period", "y": ["observed"], "title": "Anomalies"}},
        ]}],
        synthesize=[cite_findings(lambda t: "2026-08-14" in t, 1)],
    )
    analysis = ask(source["id"], "Were there unusual days for Karachi this summer?")
    assert analysis["status"] == "completed", [(s["tool"], s["status"], s["result_summary"]) for s in analysis["steps"]]
    findings = client.get(f"/api/analyses/{analysis['id']}/findings", headers=auth).json()
    anomalies = [f for f in findings if f["kind"] == "anomaly"]
    assert any("2026-08-14" in f["statement"] for f in anomalies)
    assert analysis["answer"]["headline"]
    report = client.post(f"/api/analyses/{analysis['id']}/report", headers=auth).json()
    assert "2026-08-14" in client.get(f"/api/reports/{report['id']}/html", headers=auth).text


def test_cancel_queued_analysis(client: TestClient, auth, upload, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.api.routes.conversations.enqueue_analysis", lambda _id: None)
    source = upload(data_dir / "sales.csv")
    conversation = client.post("/api/conversations", headers=auth, json={"data_source_id": source["id"]}).json()
    analysis = client.post(f"/api/conversations/{conversation['id']}/ask", headers=auth,
                           json={"question": "Revenue by region"}).json()
    busy = client.post(f"/api/conversations/{conversation['id']}/ask", headers=auth, json={"question": "Another one"})
    assert busy.status_code == 422
    cancelled = client.post(f"/api/analyses/{analysis['id']}/cancel", headers=auth).json()
    assert cancelled["status"] == "cancelled"
