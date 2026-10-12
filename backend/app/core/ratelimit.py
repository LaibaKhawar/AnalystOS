"""Fixed-window rate limiting backed by Redis.

Used for sign-in attempts (per client IP) and for questions (per user, since every question costs LLM time).
If Redis is unreachable the limiter fails open and logs it: availability of the product is preferred over
strict limiting, and the job queue would be down anyway.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.errors import AnalystError
from app.core.logging import get_logger

log = get_logger(__name__)


class RateLimited(AnalystError):
    status_code = 429
    code = "rate_limited"


@lru_cache
def _redis() -> Any:
    import redis

    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1)


def hit(key: str, limit: int, window_seconds: int) -> None:
    """Count one event for `key`; raise RateLimited when more than `limit` happen in the current window."""
    if limit <= 0:
        return
    bucket = int(time.time() // window_seconds)
    name = f"analystos:rl:{key}:{bucket}"
    try:
        client = _redis()
        pipe = client.pipeline()
        pipe.incr(name)
        pipe.expire(name, window_seconds + 5)
        count = int(pipe.execute()[0])
    except Exception:
        log.warning("rate_limit_unavailable", key=key.split(":")[0])
        return
    if count > limit:
        retry = window_seconds - int(time.time()) % window_seconds
        raise RateLimited(f"Too many requests. Try again in {retry} seconds.", details={"retry_after_seconds": retry})
