from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def test_auth_required_and_errors(client: TestClient) -> None:
    response = client.get("/api/sources")
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthorized"
    client.post("/api/auth/register", json={"email": "a@b.co", "name": "A", "password": "password-123"})
    bad = client.post("/api/auth/login", json={"email": "a@b.co", "password": "wrong-password"})
    assert bad.status_code == 401
    short = client.post("/api/auth/register", json={"email": "c@d.co", "name": "C", "password": "x"})
    assert short.status_code == 422


def test_users_cannot_see_each_others_data(client: TestClient, auth: dict[str, str], upload, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "saas_subscriptions.csv")
    other = client.post(
        "/api/auth/register", json={"email": "other@example.com", "name": "O", "password": "another-password"}
    ).json()["access_token"]
    response = client.get(f"/api/sources/{source['id']}", headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 404


def test_upload_validation(client: TestClient, auth: dict[str, str]) -> None:
    bad = client.post("/api/sources/upload", headers=auth, files={"file": ("notes.json", b"{}")})
    assert bad.status_code == 422 and "Unsupported file type" in bad.json()["error"]["message"]
    empty = client.post("/api/sources/upload", headers=auth, files={"file": ("e.csv", b"")})
    assert empty.status_code == 422


def test_excel_multi_sheet_upload_and_semantic_override(
    client: TestClient,
    auth: dict[str, str],
    upload,  # type: ignore[no-untyped-def]
    data_dir: Path,
) -> None:
    source = upload(data_dir / "sales_2026.xlsx")
    assert source["table_count"] == 3
    tables = {t["name"]: t for t in client.get(f"/api/sources/{source['id']}/tables", headers=auth).json()}
    assert set(tables) == {"transactions", "targets", "regions"}
    column = next(c for c in tables["targets"]["columns"] if c["name"] == "revenue_target")
    patched = client.patch(
        f"/api/sources/{source['id']}/columns/{column['id']}", headers=auth, json={"semantic_type": "currency_metric"}
    ).json()
    assert patched["semantic_confidence"] == 1.0 and patched["semantic_source"] == "user"


def test_sqlite_connection_is_read_only_and_password_hidden(client: TestClient, auth: dict[str, str]) -> None:
    root = get_settings().data_dir / "sqlite"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "shop.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE orders (id INTEGER, customer_email TEXT, amount REAL, created_at TEXT)")
    con.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?)",
        [(i, f"u{i}@x.io", i * 1.5, f"2026-01-{(i % 28) + 1:02d}") for i in range(200)],
    )
    con.commit()
    con.close()
    response = client.post(
        "/api/sources/connections",
        headers=auth,
        json={"name": "Shop", "kind": "sqlite", "database": "shop.sqlite", "password": "unused-secret"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready" and body["has_password"] is True
    assert "unused-secret" not in response.text and "password_encrypted" not in body
    tables = client.get(f"/api/sources/{body['id']}/tables", headers=auth).json()
    columns = {c["name"]: c for c in tables[0]["columns"]}
    assert columns["customer_email"]["is_pii"] is True
    preview = client.get(f"/api/sources/{body['id']}/tables/{tables[0]['id']}/preview", headers=auth).json()
    assert preview["masked_columns"] == ["customer_email"] and preview["rows"][0][1] == "***"
    escape = client.post(
        "/api/sources/connections", headers=auth, json={"name": "x", "kind": "sqlite", "database": "/etc/passwd"}
    )
    assert escape.status_code == 400


@pytest.mark.postgres
def test_postgres_connection_with_allowlist(client: TestClient, auth: dict[str, str]) -> None:
    url = make_url(get_settings().database_url)
    admin = create_engine(get_settings().database_url)
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS shop CASCADE"))
        conn.execute(text("CREATE SCHEMA shop"))
        conn.execute(text("CREATE TABLE shop.orders (id int, region text, amount numeric, ordered_at date)"))
        conn.execute(text("CREATE TABLE shop.secrets (id int, token text)"))
        conn.execute(
            text(
                "INSERT INTO shop.orders SELECT g, CASE WHEN g % 2 = 0 THEN 'North' ELSE 'South' END, "
                "g * 2.5, DATE '2026-01-01' + g FROM generate_series(1, 300) g"
            )
        )
    try:
        response = client.post(
            "/api/sources/connections",
            headers=auth,
            json={
                "name": "Warehouse",
                "kind": "postgresql",
                "host": url.host,
                "port": url.port,
                "database": url.database,
                "username": url.username,
                "password": url.password,
                "db_schema": "shop",
                "allowed_tables": ["orders"],
            },
        )
        assert response.status_code == 201, response.text
        tables = client.get(f"/api/sources/{response.json()['id']}/tables", headers=auth).json()
        assert [t["name"] for t in tables] == ["orders"]
        assert tables[0]["row_count"] == 300
        bad = client.post(
            "/api/sources/connections",
            headers=auth,
            json={
                "name": "Bad",
                "kind": "postgresql",
                "host": url.host,
                "port": url.port,
                "database": url.database,
                "username": url.username,
                "password": "wrong-password",
            },
        )
        assert bad.status_code == 400 and "wrong-password" not in bad.text
    finally:
        with admin.begin() as conn:
            conn.execute(text("DROP SCHEMA shop CASCADE"))


def test_health_and_metrics(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/health").json()["checks"]["database"] == "ok"
    metrics = client.get("/metrics").text
    assert "analystos_tool_calls_total" in metrics
    dashboard = client.get("/api/dashboard", headers=auth).json()
    assert {"datasets", "analyses", "total_cost_usd"} <= set(dashboard)


def test_delete_source_with_analyses(
    client: TestClient, auth: dict[str, str], agent, upload, ask, data_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.test_analysis_flows import cite_findings

    source = upload(data_dir / "saas_subscriptions.csv")
    agent.script(
        plan=[
            {
                "goal": "count",
                "steps": [
                    {
                        "id": "s1",
                        "title": "Plans",
                        "tool": "aggregate_metric",
                        "args": {"metric": {"agg": "count"}, "group_by": ["plan"]},
                    }
                ],
            }
        ],
        synthesize=[cite_findings(lambda t: "Highest" in t, 1)],
    )
    analysis = ask(source["id"], "How many customers per plan?")
    assert analysis["status"] == "completed"
    client.post(f"/api/analyses/{analysis['id']}/report", headers=auth)
    response = client.delete(f"/api/sources/{source['id']}", headers=auth)
    assert response.status_code == 204, response.text
    assert client.get(f"/api/sources/{source['id']}", headers=auth).status_code == 404
    assert client.get(f"/api/analyses/{analysis['id']}", headers=auth).status_code == 404
    assert all(s["id"] != source["id"] for s in client.get("/api/sources", headers=auth).json())


def test_failed_delete_keeps_dataset_files(
    client: TestClient,
    auth: dict[str, str],
    upload,
    data_dir: Path,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    db,
) -> None:
    from app.db.models import DatasetVersion

    source = upload(data_dir / "marketing_performance.csv")
    version = db.query(DatasetVersion).join(DatasetVersion.dataset).filter_by(data_source_id=source["id"]).one()
    assert Path(version.storage_path).is_absolute() and Path(version.storage_path).exists()

    def boom(self) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", boom)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/sources/{source['id']}", headers=auth)
    monkeypatch.undo()
    assert Path(version.storage_path).exists()  # files survive a failed delete
