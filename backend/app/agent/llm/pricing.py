"""Configurable token pricing (USD per 1M tokens). Override or extend with PRICING_FILE (YAML)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import get_settings

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    # model id prefix: (input USD / 1M tokens, output USD / 1M tokens)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet": (3.00, 15.00),
    # Local / self-hosted models have no per-token charge.
    "qwen": (0.0, 0.0),
    "llama": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "phi": (0.0, 0.0),
    "gemma": (0.0, 0.0),
    "deepseek": (0.0, 0.0),
}


@lru_cache
def price_table() -> dict[str, tuple[float, float]]:
    prices = dict(DEFAULT_PRICES)
    path: Path | None = get_settings().pricing_file
    if path and path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        for model, entry in data.items():
            prices[str(model)] = (float(entry["input"]), float(entry["output"]))
    return prices


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    table = price_table()
    match = max((key for key in table if model.lower().startswith(key.lower())), key=len, default=None)
    if match is None:
        return 0.0
    price_in, price_out = table[match]
    return round(input_tokens / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out, 6)


def is_priced(model: str) -> bool:
    return any(model.lower().startswith(k.lower()) for k in price_table())
