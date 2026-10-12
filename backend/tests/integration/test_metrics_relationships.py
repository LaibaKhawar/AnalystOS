"""Saved metric definitions and multi-table relationships."""

from __future__ import annotations

import shutil
from pathlib import Path

import openpyxl
import pandas as pd
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.models import SQLExecution
from tests.integration.test_analysis_flows import cite_findings


def test_metric_definitions_are_validated(client: TestClient, auth: dict[str, str], upload, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    url = f"/api/sources/{source['id']}/metrics"
    base = {"name": "avg_order_value", "label": "Average order value", "table": "sales"}
    for bad, message in [
        ("revenue", "must aggregate"),
        ("SUM(revenu)", "Unknown column"),
        ("(SELECT SUM(revenue) FROM sales)", "not a query"),
        ("SUM(revenue); DROP TABLE sales", "sql"),  # rejected by the parser or the validator
        ("SUM(read_csv('/etc/passwd'))", "validator"),
    ]:
        response = client.post(url, headers=auth, json={**base, "expression": bad})
        assert response.status_code == 422, (bad, response.text)
        assert message.lower() in response.json()["error"]["message"].lower(), (bad, response.text)
    created = client.post(
        url, headers=auth, json={**base, "expression": "sum(revenue) / count(*)", "format": "currency"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["expression"] == "SUM(revenue) / COUNT(*)"
    assert client.post(url, headers=auth, json={**base, "expression": "AVG(revenue)"}).status_code == 422  # duplicate
    assert [m["name"] for m in client.get(url, headers=auth).json()] == ["avg_order_value"]


def test_agent_uses_saved_metric_definition(client: TestClient, auth, agent, upload, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "sales.csv")
    client.post(
        f"/api/sources/{source['id']}/metrics",
        headers=auth,
        json={
            "name": "units_per_order",
            "label": "Units per order",
            "table": "sales",
            "expression": "SUM(units) * 1.0 / COUNT(*)",
            "filters": [{"column": "customer_segment", "op": "=", "value": "Enterprise"}],
        },
    )
    llm = agent.script(
        plan=[
            {
                "goal": "Units per order",
                "steps": [
                    {"id": "s1", "title": "Metric", "tool": "compute_metric", "args": {"name": "units_per_order"}}
                ],
            }
        ],
        synthesize=[cite_findings(lambda t: "Saved metric" in t, 1)],
    )
    analysis = ask(source["id"], "What is our units per order?")
    assert analysis["status"] == "completed", analysis["error"]
    assert "SAVED METRICS" in llm.calls[0][1][-1]["content"]
    frame = pd.read_csv(data_dir / "sales.csv")
    enterprise = frame[frame.customer_segment == "Enterprise"]
    expected = enterprise.units.sum() / len(enterprise)
    findings = client.get(f"/api/analyses/{analysis['id']}/findings", headers=auth).json()
    assert abs(findings[0]["values"]["value"] - expected) < 1e-6
    sql = db.query(SQLExecution).filter(SQLExecution.analysis_id == analysis["id"]).one()
    assert "Enterprise" in sql.sql_executed  # the definition's own filter is applied


def test_workbook_sheet_relationships(client: TestClient, auth: dict[str, str], upload, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    wb = openpyxl.Workbook()
    customers = wb.active
    customers.title = "Customers"
    customers.append(["customer_id", "segment"])
    for i in range(1, 21):
        customers.append([f"C{i:03d}", "Enterprise" if i % 4 == 0 else "SMB"])
    orders = wb.create_sheet("Orders")
    orders.append(["order_id", "customer_id", "amount"])
    for i in range(1, 101):
        orders.append([i, f"C{(i % 20) + 1:03d}", float(i)])
    path = tmp_path / "crm.xlsx"
    wb.save(path)
    source = upload(path)
    relationships = client.get(f"/api/sources/{source['id']}", headers=auth).json()["ingestion_report"]["relationships"]
    assert [(r["child_table"], r["child_column"], r["parent_table"]) for r in relationships] == [
        ("orders", "customer_id", "customers")
    ]
    assert relationships[0]["containment"] == 1.0


def test_chinook_declared_foreign_keys_and_join(client: TestClient, auth, agent, ask, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import DataSource

    root = get_settings().data_dir / "sqlite"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy(data_dir / "chinook.sqlite", root / "chinook.sqlite")
    created = client.post(
        "/api/sources/connections",
        headers=auth,
        json={"name": "Chinook", "kind": "sqlite", "database": "chinook.sqlite"},
    )
    assert created.status_code == 201, created.text
    source = db.get(DataSource, created.json()["id"])
    rels = {
        (r["child_table"], r["child_column"], r["parent_table"], r["source"]) for r in source.options["relationships"]
    }
    assert ("Invoice", "CustomerId", "Customer", "declared") in rels
    assert ("InvoiceLine", "TrackId", "Track", "declared") in rels
    join_sql = (
        "SELECT c.Country AS country, SUM(i.Total) AS revenue FROM Invoice i "
        "JOIN Customer c ON i.CustomerId = c.CustomerId GROUP BY c.Country ORDER BY revenue DESC"
    )
    llm = agent.script(
        plan=[
            {
                "goal": "Revenue by country",
                "steps": [{"id": "s1", "title": "Join", "tool": "execute_sql", "args": {"sql": join_sql}}],
            }
        ],
        synthesize=[cite_findings(lambda t: "country=USA" in t, 1)],
    )
    analysis = ask(created.json()["id"], "Which customer country brings the most invoice revenue?")
    assert analysis["status"] == "completed", analysis["error"]
    assert "RELATIONSHIPS" in llm.calls[0][1][-1]["content"]
    assert "USA" in analysis["answer"]["headline"]
