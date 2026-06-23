from __future__ import annotations

import re
from datetime import datetime, timezone

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.http_json import fetch_text

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
_CACHE_KEY = "amfi:nav_all"
_CACHE_TTL = 6 * 3600


def _norm_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for token in ("direct plan", "direct", "growth", "regular plan", "regular"):
        s = s.replace(token, " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_amfi_nav_all(text: str) -> dict[str, dict]:
    """Parse AMFI NAVAll.txt into {scheme_code: {name, nav, date}}."""
    rows: dict[str, dict] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        code, _, _, name, nav_str, nav_date = parts[:6]
        if not code.isdigit():
            continue
        try:
            nav = float(nav_str)
        except ValueError:
            continue
        rows[code] = {"scheme_code": code, "name": name, "nav": nav, "nav_date": nav_date}
    return rows


def _name_index(rows: dict[str, dict]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for row in rows.values():
        key = _norm_name(row["name"])
        if key and key not in idx:
            idx[key] = row
    return idx


def fetch_amfi_nav_map(*, force: bool = False, ttl: int = _CACHE_TTL) -> dict[str, dict]:
    if not force and ttl > 0:
        hit = cache_get_json(_CACHE_KEY)
        if isinstance(hit, dict) and hit.get("rows"):
            return hit["rows"]

    text = fetch_text(AMFI_NAV_URL, timeout=20, retries=3)
    rows = parse_amfi_nav_all(text)
    if ttl > 0 and rows:
        cache_set_json(
            _CACHE_KEY,
            {"rows": rows, "fetched_at": datetime.now(timezone.utc).isoformat()},
            ttl,
        )
    return rows


def lookup_amfi_nav(
    fund_cfg: dict,
    rows: dict[str, dict] | None = None,
    name_index: dict[str, dict] | None = None,
) -> dict | None:
    rows = rows or fetch_amfi_nav_map()
    code = str(fund_cfg.get("amfi_scheme_code") or "").strip()
    if code and code in rows:
        return rows[code]

    idx = name_index or _name_index(rows)
    cfg_name = _norm_name(fund_cfg.get("name", ""))
    if not cfg_name:
        return None

    if cfg_name in idx:
        return idx[cfg_name]

    for key, row in idx.items():
        if cfg_name in key or key in cfg_name:
            return row
    return None
