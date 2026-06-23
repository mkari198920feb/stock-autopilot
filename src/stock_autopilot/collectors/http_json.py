from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

_SSL_CTX = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
    retries: int = 3,
    backoff: float = 0.6,
) -> Any:
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(backoff * (attempt + 1))
    if last_err:
        raise last_err
    raise RuntimeError("fetch_json failed")


def fetch_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
    retries: int = 3,
    backoff: float = 0.6,
) -> str:
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(backoff * (attempt + 1))
    if last_err:
        raise last_err
    raise RuntimeError("fetch_text failed")
