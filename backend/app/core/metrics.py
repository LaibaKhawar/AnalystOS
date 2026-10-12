"""Prometheus metrics. Exposed at /metrics by the API; the worker exposes its own registry port."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

ANALYSIS_LATENCY = Histogram(
    "analystos_analysis_seconds",
    "End-to-end analysis latency",
    ["status"],
    buckets=(1, 5, 10, 20, 40, 60, 120, 240, 480, 900),
)
TOOL_LATENCY = Histogram(
    "analystos_tool_seconds",
    "Tool execution latency",
    ["tool", "status"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
TOOL_CALLS = Counter("analystos_tool_calls_total", "Tool calls by outcome", ["tool", "status"])
TOOL_RETRIES = Counter("analystos_tool_retries_total", "Tool retries after a failure", ["tool"])
LLM_TOKENS = Counter("analystos_llm_tokens_total", "LLM tokens", ["model", "direction"])
LLM_CALLS = Counter("analystos_llm_calls_total", "LLM calls", ["model", "purpose", "status"])
LLM_LATENCY = Histogram(
    "analystos_llm_seconds",
    "LLM call latency",
    ["model", "purpose"],
    buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160),
)
QUERY_DURATION = Histogram(
    "analystos_query_seconds",
    "SQL query duration",
    ["dialect", "status"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 20),
)
SQL_BLOCKED = Counter("analystos_sql_blocked_total", "SQL statements rejected by the validator", ["reason"])
SANDBOX_RUNS = Counter("analystos_sandbox_runs_total", "Sandbox executions by outcome", ["status"])
CLAIMS_VERIFIED = Counter("analystos_claims_total", "Claims by verification outcome", ["status"])
