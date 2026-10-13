"""OpenAI-compatible chat client: OpenAI, Azure OpenAI, Ollama (/v1), vLLM, LM Studio, OpenRouter...

Reasoning models may emit <think>...</think> blocks; these are private chain-of-thought and are
stripped before anything is stored, logged or shown.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.agent.llm.base import LLMProvider, LLMResponse, Usage
from app.core.config import Settings, get_settings
from app.core.errors import LLMError
from app.core.logging import get_logger
from app.core.metrics import LLM_CALLS, LLM_LATENCY, LLM_TOKENS
from app.core.tracing import span

log = get_logger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "<think>" in text.lower():  # unterminated block: drop everything up to the end of it
        text = text.split("</think>")[-1] if "</think>" in text else ""
    return text.strip()


_MAX_ATTEMPTS = 6
_MAX_WAIT_SECONDS = 60.0


def _retry_after(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait after a 429: the provider's Retry-After (or Groq-style reset header), else backoff."""
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = response.headers.get(header)
        if not value:
            continue
        match = re.fullmatch(r"(?:(\d+)m)?(\d+(?:\.\d+)?)s?|(\d+(?:\.\d+)?)ms", value.strip())
        if match:
            if match.group(3):
                seconds = float(match.group(3)) / 1000
            else:
                seconds = float(match.group(1) or 0) * 60 + float(match.group(2))
            return min(max(seconds, 0.5), _MAX_WAIT_SECONDS)
    return min(2.0 * 2**attempt, _MAX_WAIT_SECONDS)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None, *, model: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.llm_model
        # Serverless GPU hosts (Modal) answer a request that outlives a cold start with a 303 to a result URL.
        self._client = httpx.Client(timeout=self.settings.llm_timeout_seconds, follow_redirects=True)

    def _endpoint(self) -> tuple[str, dict[str, str]]:
        s = self.settings
        base = s.llm_base_url.rstrip("/")
        if s.llm_provider == "azure_openai":
            url = f"{base}/openai/deployments/{self.model}/chat/completions?api-version={s.azure_api_version}"
            return url, {"api-key": s.llm_api_key}
        return f"{base}/chat/completions", {"Authorization": f"Bearer {s.llm_api_key}"}

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        with span(f"llm.{purpose}", **{"llm.model": self.model, "llm.purpose": purpose}) as current:
            response = self._complete(
                messages, purpose=purpose, json_mode=json_mode, temperature=temperature, max_tokens=max_tokens
            )
            current.set_attribute("llm.input_tokens", response.usage.input_tokens)
            current.set_attribute("llm.output_tokens", response.usage.output_tokens)
            current.set_attribute("llm.latency_ms", response.latency_ms)
            return response

    def _complete(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        url, headers = self._endpoint()
        msgs = [dict(m) for m in messages]
        if self.settings.llm_disable_thinking and "qwen3" in self.model.lower() and msgs:
            msgs[-1]["content"] = f"{msgs[-1]['content']}\n/no_think"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.llm_max_output_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.post(url, json=body, headers=headers)
                if response.status_code == 429 and attempt < _MAX_ATTEMPTS - 1:
                    # Hosted free tiers limit tokens per minute; wait as long as the provider asks.
                    time.sleep(_retry_after(response, attempt))
                    continue
                if response.status_code in {500, 502, 503, 504} and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if response.status_code == 413:
                    raise LLMError(
                        "This request is larger than the model provider allows (free tiers cap tokens per request). "
                        "Try a dataset with fewer tables or columns, or configure a model without that limit."
                    )
                if response.status_code >= 400:
                    raise LLMError(f"LLM provider returned HTTP {response.status_code}: {response.text[:200]}")
                data = response.json()
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                LLM_CALLS.labels(model=self.model, purpose=purpose, status="error").inc()
                raise LLMError(f"LLM provider unreachable: {exc.__class__.__name__}") from exc
        else:  # pragma: no cover - loop always breaks or raises
            raise LLMError(f"LLM provider failed: {last_error}")

        latency = int((time.perf_counter() - started) * 1000)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage_raw = data.get("usage") or {}
        usage = Usage(int(usage_raw.get("prompt_tokens") or 0), int(usage_raw.get("completion_tokens") or 0))
        LLM_CALLS.labels(model=self.model, purpose=purpose, status="success").inc()
        LLM_LATENCY.labels(model=self.model, purpose=purpose).observe(latency / 1000)
        LLM_TOKENS.labels(model=self.model, direction="input").inc(usage.input_tokens)
        LLM_TOKENS.labels(model=self.model, direction="output").inc(usage.output_tokens)
        log.info(
            "llm_call",
            purpose=purpose,
            model=self.model,
            latency_ms=latency,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        return LLMResponse(
            content=strip_reasoning(message.get("content") or ""),
            model=str(data.get("model") or self.model),
            usage=usage,
            latency_ms=latency,
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason"),
        )

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        s = self.settings
        base = (s.embedding_base_url or "").rstrip("/")
        if not base:
            return None
        try:
            response = self._client.post(
                f"{base}/embeddings",
                json={"model": s.embedding_model, "input": texts},
                headers={"Authorization": f"Bearer {s.embedding_api_key or s.llm_api_key}"},
            )
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]
        except Exception as exc:
            log.warning("embedding_failed", error=exc.__class__.__name__)
            return None


def get_provider() -> LLMProvider:
    return OpenAICompatibleProvider()
