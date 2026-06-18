from __future__ import annotations

from stock_autopilot.universe import load_config

_INDIA_MAP: dict[str, str] | None = None


def _load_india_map() -> dict[str, str]:
    """Map bare NSE codes and aliases → Yahoo tickers (e.g. SBIN → SBIN.NS)."""
    global _INDIA_MAP
    if _INDIA_MAP is not None:
        return _INDIA_MAP

    mapping: dict[str, str] = {}
    cfg = load_config()
    for raw in cfg.get("india_desk", {}).get("nse_universe") or []:
        sym = raw.strip().upper()
        if not sym:
            continue
        if sym.endswith(".NS") or sym.endswith(".BO"):
            bare = sym.rsplit(".", 1)[0]
            mapping[sym] = sym
            mapping[bare] = sym
        else:
            yahoo = f"{sym}.NS"
            mapping[sym] = yahoo
            mapping[yahoo] = yahoo

    _INDIA_MAP = mapping
    return mapping


def to_yahoo_symbol(symbol: str) -> str:
    """Normalize a display or NSE code to a Yahoo Finance ticker."""
    s = symbol.strip().upper()
    if not s:
        return s

    if s.startswith("^") or "=" in s or s.endswith("-USD") or s.endswith("=F"):
        return s

    if "." in s:
        return s

    if s in ("BTC", "ETH", "SOL", "BNB", "DOGE", "XRP", "ADA", "AVAX"):
        return f"{s}-USD"

    india = _load_india_map()
    if s in india:
        return india[s]

    return s


def display_symbol(yahoo_symbol: str) -> str:
    """Human-friendly NSE code for UI (SBIN.NS → SBIN)."""
    s = yahoo_symbol.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s.rsplit(".", 1)[0]
    return s
