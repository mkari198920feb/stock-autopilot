from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Any

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

_SSL_CTX = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()


def fetch_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 12) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode())
