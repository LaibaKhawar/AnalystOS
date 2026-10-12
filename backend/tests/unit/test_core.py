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
