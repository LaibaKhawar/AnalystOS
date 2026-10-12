from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.orchestrator import AnalysisRunner
from app.db.session import get_session_factory
from app.main import app
from tests.fakes import ScriptedLLM


@pytest.fixture
def client(db) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]  # db fixture truncates afterwards
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/register", json={"email": "analyst@example.com", "name": "Analyst",
                                                        "password": "a-strong-password"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class AgentHarness:
    """Runs analyses synchronously with a scripted LLM instead of enqueueing them on Celery."""

    def __init__(self) -> None:
        self.llm = ScriptedLLM()

    def script(self, **scripts: list[Any]) -> ScriptedLLM:
        self.llm = ScriptedLLM(scripts)
        return self.llm

    def run(self, analysis_id: str) -> None:
        session = get_session_factory()()
        try:
            AnalysisRunner(session, self.llm, emit_events=True).run(analysis_id)
        finally:
            session.close()


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> AgentHarness:
    harness = AgentHarness()
    monkeypatch.setattr("app.api.routes.conversations.enqueue_analysis", harness.run)
    monkeypatch.setattr("app.api.routes.analyses.enqueue_analysis", harness.run)
    return harness


@pytest.fixture
def upload(client: TestClient, auth: dict[str, str]) -> Callable[[Path], dict[str, Any]]:
    def _upload(path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            response = client.post("/api/sources/upload", headers=auth, files={"file": (path.name, handle)})
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    return _upload


@pytest.fixture
def ask(client: TestClient, auth: dict[str, str]) -> Callable[..., dict[str, Any]]:
    def _ask(source_id: str, question: str, conversation_id: str | None = None) -> dict[str, Any]:
        if conversation_id is None:
            conversation = client.post("/api/conversations", headers=auth, json={"data_source_id": source_id})
            assert conversation.status_code == 201, conversation.text
            conversation_id = conversation.json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/ask", headers=auth, json={"question": question})
        assert response.status_code == 202, response.text
        analysis = client.get(f"/api/analyses/{response.json()['id']}", headers=auth).json()
        analysis["conversation_id"] = conversation_id
        return analysis  # type: ignore[no-any-return]

    return _ask
