from __future__ import annotations

import pytest

from app.agent.llm.base import LLMResponse, Usage
from app.agent.llm.openai_compat import strip_reasoning
from app.agent.llm.pricing import estimate_cost
from app.agent.llm.structured import CallLog, extract_json, generate_structured
from app.agent.schemas import Plan
from app.core.errors import AuthError, LLMError
from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
from tests.fakes import ScriptedLLM


def test_password_hashing_and_tokens() -> None:
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed) and not verify_password("wrong", hashed)
    assert decode_access_token(create_access_token("usr_1")) == "usr_1"
    with pytest.raises(AuthError):
        decode_access_token("not-a-token")


def test_credential_encryption_roundtrip() -> None:
    cipher = encrypt_secret("s3cret!")
    assert "s3cret" not in cipher and decrypt_secret(cipher) == "s3cret!"


def test_cost_estimation_configurable() -> None:
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)
    assert estimate_cost("gpt-4o-mini-2024-07-18", 1000, 0) == pytest.approx(0.00015)
    assert estimate_cost("qwen3:8b", 10_000, 10_000) == 0.0
    assert estimate_cost("unknown-model", 10_000, 10_000) == 0.0


def test_reasoning_blocks_are_stripped() -> None:
    assert strip_reasoning('<think>secret plan</think>\n{"a": 1}') == '{"a": 1}'
    assert strip_reasoning("<think>unterminated") == ""


def test_extract_json_variants() -> None:
    assert extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('Here you go: {"b": [1, 2]} thanks') == {"b": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_structured_generation_repairs_once_then_fails() -> None:
    good = {"goal": "g", "steps": [{"id": "s1", "title": "t", "tool": "list_tables"}]}
    llm = ScriptedLLM({"plan": ["not json", good]})
    log = CallLog()
    plan = generate_structured(llm, [{"role": "user", "content": "q"}], Plan, purpose="plan", log=log)
    assert plan.steps[0].tool == "list_tables" and log.calls == 2
    bad = ScriptedLLM({"plan": ["x", "y", "z"]})
    with pytest.raises(LLMError):
        generate_structured(bad, [{"role": "user", "content": "q"}], Plan, purpose="plan", log=CallLog())


def test_call_log_accumulates() -> None:
    log = CallLog()
    log.record(LLMResponse("x", "m", Usage(10, 5), 100), "plan")
    log.record(LLMResponse("x", "m", Usage(3, 2), 50), "plan")
    assert (log.usage.input_tokens, log.usage.output_tokens, log.calls) == (13, 7, 2)


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3100, https://app.example.com")
    assert Settings().cors_origins == ["http://localhost:3100", "https://app.example.com"]  # type: ignore[call-arg]


def test_blank_optional_settings_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("PRICING_FILE", "")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.pricing_file is None and settings.embedding_base_url is None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@db:5432/x", "postgresql+psycopg://u:p@db:5432/x"),
        ("postgresql://u:p@db/x", "postgresql+psycopg://u:p@db/x"),
        ("postgresql+psycopg://u:p@db/x", "postgresql+psycopg://u:p@db/x"),
    ],
)
def test_hosted_postgres_urls_get_the_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch, given: str, expected: str
) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings().database_url == expected  # type: ignore[call-arg]


def test_result_rows_are_json_safe() -> None:
    import json

    import numpy as np

    from app.agent.context import json_rows

    rows = json_rows([[float("nan"), np.float64("nan"), np.int64(3), float("inf"), "Enterprise", None]])
    assert rows == [[None, None, 3, None, "Enterprise", None]]
    json.dumps(rows, allow_nan=False)  # what Postgres JSONB accepts


def test_every_runtime_dependency_is_pinned_in_the_lockfile() -> None:
    """The Docker image installs requirements.lock; a dependency missing there only fails in production."""
    import re
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    declared = tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"]
    pinned = {
        re.split(r"==", line)[0].strip().lower().replace("_", "-")
        for line in (root / "requirements.lock").read_text().splitlines()
        if "==" in line
    }
    names = {re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower().replace("_", "-") for spec in declared}
    assert sorted(names - pinned) == []


def test_thread_pool_workers_set_up_tracing_without_prefork_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    from celery.concurrency import prefork, thread

    from app.workers import celery_app as worker_module

    calls: list[str] = []
    monkeypatch.setattr(worker_module, "_init_runtime", lambda: calls.append("init"))
    monkeypatch.setattr(worker_module.settings, "metrics_enabled", False)

    class Worker:
        def __init__(self, pool_cls: object) -> None:
            self.pool_cls = pool_cls

    worker_module._on_worker_init(sender=Worker(thread.TaskPool))
    assert calls == ["init"]  # threads: set up in this process
    worker_module._on_worker_init(sender=Worker(prefork.TaskPool))
    assert calls == ["init"]  # prefork: left to worker_process_init in each child


def test_llm_client_follows_cold_start_redirects() -> None:
    import json

    import httpx

    from app.agent.llm.openai_compat import OpenAICompatibleProvider
    from app.core.config import get_settings

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(303, headers={"location": "https://gpu.example/result/1"})
        body = {
            "model": "m",
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        return httpx.Response(200, content=json.dumps(body))

    provider = OpenAICompatibleProvider(get_settings(), model="m")
    provider._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    assert provider._client.follow_redirects is True
    response = provider.complete([{"role": "user", "content": "hi"}], purpose="plan")
    assert response.content == '{"ok": true}'
    assert OpenAICompatibleProvider(get_settings(), model="m")._client.follow_redirects is True
