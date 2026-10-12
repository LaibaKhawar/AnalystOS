"""Roles, sharing, refresh tokens, rate limits and evaluation visibility."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.models import EvaluationRun, User


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register", json={"email": email, "name": email.split("@")[0], "password": "a-strong-password"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_sharing_grants_exact_access(client: TestClient, auth: dict[str, str], upload, data_dir: Path, db) -> None:  # type: ignore[no-untyped-def]
    source = upload(data_dir / "saas_subscriptions.csv")
    bob = _register(client, "bob@example.com")
    assert client.get(f"/api/sources/{source['id']}", headers=bob).status_code == 404  # not shared yet

    share = client.post(
        f"/api/sources/{source['id']}/shares", headers=auth, json={"email": "bob@example.com", "role": "viewer"}
    )
    assert share.status_code == 201
    listed = client.get("/api/sources", headers=bob).json()
    assert [(s["id"], s["access"], s["owned"]) for s in listed] == [(source["id"], "read", False)]
    assert client.get(f"/api/sources/{source['id']}/tables", headers=bob).status_code == 200
    ask = client.post("/api/conversations", headers=bob, json={"data_source_id": source["id"]})
    assert ask.status_code == 403 and "read-only" in ask.json()["error"]["message"]
    assert client.delete(f"/api/sources/{source['id']}", headers=bob).status_code == 403
    assert client.get(f"/api/sources/{source['id']}/shares", headers=bob).status_code == 403

    client.post(
        f"/api/sources/{source['id']}/shares", headers=auth, json={"email": "bob@example.com", "role": "analyst"}
    )
    assert client.post("/api/conversations", headers=bob, json={"data_source_id": source["id"]}).status_code == 201

    shares = client.get(f"/api/sources/{source['id']}/shares", headers=auth).json()
    assert client.delete(f"/api/sources/{source['id']}/shares/{shares[0]['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/sources/{source['id']}", headers=bob).status_code == 404


def test_viewer_role_is_read_only(client: TestClient, auth: dict[str, str], db) -> None:  # type: ignore[no-untyped-def]
    viewer = _register(client, "vera@example.com")
    user = db.query(User).filter(User.email == "vera@example.com").one()
    admin_users = client.get("/api/admin/users", headers=auth).json()  # first account is admin
    assert {u["email"] for u in admin_users} >= {"analyst@example.com", "vera@example.com"}
    assert (
        client.patch(f"/api/admin/users/{user.id}/role", headers=auth, json={"role": "viewer"}).json()["role"]
        == "viewer"
    )
    upload = client.post("/api/sources/upload", headers=viewer, files={"file": ("t.csv", b"a,b\n1,2\n")})
    assert upload.status_code == 403
    assert client.get("/api/admin/users", headers=viewer).status_code == 403


def test_refresh_token_rotation_and_reuse_detection(client: TestClient) -> None:
    first = client.post(
        "/api/auth/register", json={"email": "rt@example.com", "name": "R", "password": "a-strong-password"}
    ).json()
    rotated = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200 and rotated.json()["refresh_token"] != first["refresh_token"]
    # Replaying the old token is treated as theft: it fails and revokes the newer session too.
    assert client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401
    again = client.post("/api/auth/login", json={"email": "rt@example.com", "password": "a-strong-password"}).json()
    assert client.post("/api/auth/logout", json={"refresh_token": again["refresh_token"]}).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": again["refresh_token"]}).status_code == 401


def test_login_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import redis

    from app.core.config import get_settings

    try:
        redis.Redis.from_url(get_settings().redis_url, socket_timeout=1).ping()
    except Exception:
        pytest.skip("Redis not available")
    monkeypatch.setattr(get_settings(), "login_rate_per_minute", 3)
    headers = {"X-Forwarded-For": "203.0.113.77"}
    codes = [
        client.post(
            "/api/auth/login", headers=headers, json={"email": "nobody@example.com", "password": "wrong-password"}
        ).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_evaluation_runs_visible_to_owner_or_system(client: TestClient, auth: dict[str, str], db) -> None:  # type: ignore[no-untyped-def]
    other = _register(client, "eve@example.com")
    owner = db.query(User).filter(User.email == "analyst@example.com").one()
    db.add_all(
        [
            EvaluationRun(suite="core", model="m", status="completed"),
            EvaluationRun(suite="mine", model="m", status="completed", user_id=owner.id),
        ]
    )
    db.commit()
    assert {r["suite"] for r in client.get("/api/evaluations", headers=auth).json()} == {"core", "mine"}
    assert {r["suite"] for r in client.get("/api/evaluations", headers=other).json()} == {"core"}
