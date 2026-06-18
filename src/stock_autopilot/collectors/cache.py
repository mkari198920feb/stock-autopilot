from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from stock_autopilot.db import cache_delete_expired, cache_get_raw, cache_set_raw

T = TypeVar("T")


def cache_get_json(key: str) -> dict | list | None:
    raw = cache_get_raw(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_set_json(key: str, value: dict | list, ttl_seconds: int) -> None:
    cache_set_raw(key, json.dumps(value), ttl_seconds)


def cached(key: str, ttl_seconds: int, fetch_fn: Callable[[], T | None]) -> T | None:
    hit = cache_get_json(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    val = fetch_fn()
    if val is not None:
        if isinstance(val, (dict, list)):
            cache_set_json(key, val, ttl_seconds)
        else:
            cache_set_raw(key, str(val), ttl_seconds)
    return val


def init_cache() -> None:
    cache_delete_expired()
