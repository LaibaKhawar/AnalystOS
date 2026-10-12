"""Scheduled analyses, anomaly alerts and webhook safety."""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ValidationFailed
from app.db.models import Alert, Analysis, Schedule
from app.services import schedules as schedule_service
from tests.integration.test_analysis_flows import cite_findings


def _resolve_to(ip: str):  # type: ignore[no-untyped-def]
    def fake(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    return fake


@pytest.mark.parametrize(
    ("url", "ip", "ok"),
    [
        ("https://hooks.example.com/x", "93.184.215.14", True),
        ("https://internal.example.com/x", "10.0.0.5", False),
        ("https://localhost/x", "127.0.0.1", False),
        ("https://metadata.example.com/x", "169.254.169.254", False),
        ("http://hooks.example.com/x", "93.184.215.14", False),
        ("ftp://hooks.example.com/x", "93.184.215.14", False),
    ],
)
def test_webhook_ssrf_guard(monkeypatch: pytest.MonkeyPatch, url: str, ip: str, ok: bool) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to(ip))
    if ok:
        assert schedule_service.validate_webhook(url) == url
    else:
        with pytest.raises(ValidationFailed):
            schedule_service.validate_webhook(url)


def test_schedule_runs_and_alerts_on_anomalies(  # type: ignore[no-untyped-def]
    client: TestClient, auth, agent, upload, data_dir: Path, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to("93.184.215.14"))
    sent: list[dict[str, Any]] = []

    class Response:
        status_code = 200

    monkeypatch.setattr(schedule_service.httpx, "post", lambda url, json, **_: sent.append(json) or Response())
    source = upload(data_dir / "sales.csv")
    too_often = client.post(
        "/api/schedules",
        headers=auth,
        json={"data_source_id": source["id"], "name": "x", "question": "Any unusual days?", "interval_minutes": 1},
    )
    assert too_often.status_code == 422
    created = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "data_source_id": source["id"],
            "name": "Karachi daily watch",
            "interval_minutes": 60 * 24,
            "question": "Were there unusual revenue days for Karachi this summer?",
            "alert_min_severity": "medium",
            "webhook_url": "https://hooks.example.com/analystos",
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    assert schedule_service.dispatch_due(db, datetime.now(UTC)) == []  # not due yet
    started = schedule_service.dispatch_due(db, datetime.now(UTC) + timedelta(days=2))
    assert len(started) == 1
    agent.script(
        plan=[
            {
                "goal": "Karachi anomalies",
                "steps": [
                    {
                        "id": "s1",
                        "title": "Detect",
                        "tool": "detect_anomalies",
                        "args": {
                            "metric": {"column": "revenue"},
                            "time_grain": "day",
                            "period": "2026-06-01..2026-09-30",
                            "filters": [{"column": "region", "op": "=", "value": "Karachi"}],
                            "threshold": 3.5,
                        },
                    }
                ],
            }
        ],
        synthesize=[cite_findings(lambda t: "2026-08-14" in t, 1)],
    )
    agent.run(started[0])
    db.expire_all()
    schedule = db.get(Schedule, schedule_id)
    alert = schedule_service.create_alerts(db, schedule, db.get(Analysis, started[0]))
    assert alert is not None and alert.severity in {"medium", "high"} and "2026-08-14" in alert.message
    assert alert.delivery_status == "sent" and sent[0]["id"] == alert.id
    assert schedule.next_run_at > datetime.now(UTC) + timedelta(hours=23)

    listed = client.get("/api/alerts?unread_only=true", headers=auth).json()
    assert [a["id"] for a in listed] == [alert.id]
    assert client.post(f"/api/alerts/{alert.id}/read", headers=auth).json()["read_at"]
    assert client.get("/api/alerts?unread_only=true", headers=auth).json() == []


def test_failed_scheduled_run_raises_alert_and_run_now(  # type: ignore[no-untyped-def]
    client: TestClient, auth, upload, data_dir: Path, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("app.api.routes.schedules.enqueue_scheduled", lambda a, s: calls.append((a, s)))
    source = upload(data_dir / "sales.csv")
    created = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "data_source_id": source["id"],
            "name": "Weekly",
            "question": "Total revenue?",
            "interval_minutes": 10080,
        },
    )
    schedule_id = created.json()["id"]
    assert client.post(f"/api/schedules/{schedule_id}/run", headers=auth).status_code == 202
    assert calls and calls[0][1] == schedule_id
    analysis = db.get(Analysis, calls[0][0])
    analysis.status, analysis.error = "failed", "LLM unreachable"
    db.commit()
    alert = schedule_service.create_alerts(db, db.get(Schedule, schedule_id), analysis)
    assert alert is not None and alert.severity == "high" and alert.delivery_status == "not_configured"
    assert db.query(Alert).count() == 1


def test_schedule_update_rules_status_and_cleanup(  # type: ignore[no-untyped-def]
    client: TestClient, auth, upload, data_dir: Path, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models import Conversation

    monkeypatch.setattr("app.api.routes.schedules.enqueue_scheduled", lambda a, s: None)
    sales = upload(data_dir / "sales.csv")
    saas = upload(data_dir / "saas_subscriptions.csv")
    body = {"data_source_id": sales["id"], "name": "Daily", "question": "Total revenue?", "interval_minutes": 1440}
    schedule = client.post("/api/schedules", headers=auth, json=body).json()
    moved = client.put(f"/api/schedules/{schedule['id']}", headers=auth, json={**body, "data_source_id": saas["id"]})
    assert moved.status_code == 422 and "cannot be changed" in moved.json()["error"]["message"]
    client.post(f"/api/schedules/{schedule['id']}/run", headers=auth)
    listed = client.get("/api/schedules", headers=auth).json()
    assert listed[0]["last_status"] == "queued"
    assert client.get("/api/alerts/unread-count", headers=auth).json() == {"unread": 0}
    assert client.delete(f"/api/schedules/{schedule['id']}", headers=auth).status_code == 204
    assert db.get(Conversation, schedule["conversation_id"]) is None
