from __future__ import annotations

from pathlib import Path

import yaml

from stock_autopilot.config import settings

DEFAULT_NYSE_FILE = "data/universe/nyse.txt"


def load_config() -> dict:
    with open(settings.config_path) as f:
        return yaml.safe_load(f)


def _resolve_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = settings.project_root / p
    return p


def load_global_desk_config(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    gd = cfg.get("global_desk", {})
    path = gd.get("markets_file")
    if path:
        p = _resolve_path(path)
        if p.exists():
            with open(p) as f:
                extra = yaml.safe_load(f) or {}
            merged = {**gd, **extra.get("global_desk", extra)}
            return merged
    return gd


def brand_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    apex = cfg.get("apex", {})
    name = apex.get("brand_name", "LUMIQ")
    global_name = apex.get("global_platform_name", name)
    return {
        "brand_name": name,
        "global_platform_name": global_name,
        "research_header": f"{name.upper()} — EQUITY RESEARCH",
        "global_research_header": f"{global_name.upper()} — EQUITY RESEARCH",
        "india_header": f"{name.upper()} — INDIA EQUITY RESEARCH",
        "crypto_header": f"{global_name.upper()} — CRYPTO DESK",
    }


def load_nyse_tickers(cfg: dict | None = None) -> list[str]:
    """NYSE common equities from data/universe/nyse.txt (one Yahoo symbol per line)."""
    cfg = cfg or load_config()
    rel = (cfg.get("universe") or {}).get("nyse_file", DEFAULT_NYSE_FILE)
    path = _resolve_path(rel)
    if not path.exists():
        return []

    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.append(line.upper())
    return sorted(set(tickers))


def north_america_tickers(cfg: dict | None = None) -> list[str]:
    """Full NYSE file plus any extra symbols listed under regions.north_america."""
    cfg = cfg or load_config()
    extras = cfg.get("regions", {}).get("north_america") or []
    merged = load_nyse_tickers(cfg) + [s.strip().upper() for s in extras if s.strip()]
    return sorted(set(merged))


def all_tickers(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    tickers: list[str] = []
    for region, symbols in cfg.get("regions", {}).items():
        if region == "north_america":
            tickers.extend(north_america_tickers(cfg))
        else:
            tickers.extend(symbols)
    gd = load_global_desk_config(cfg)
    for market in (gd.get("markets") or {}).values():
        tickers.extend(market.get("tickers") or [])
    return sorted(set(tickers))


def ticker_region_map(cfg: dict | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    mapping: dict[str, str] = {}
    for region, symbols in cfg.get("regions", {}).items():
        label = region.replace("_", " ").title()
        if region == "north_america":
            for sym in north_america_tickers(cfg):
                mapping[sym] = label
        else:
            for sym in symbols:
                mapping[sym] = label
    gd = load_global_desk_config(cfg)
    for market_id, market in (gd.get("markets") or {}).items():
        label = market.get("label", market_id)
        for sym in market.get("tickers") or []:
            mapping[sym] = label
    return mapping


def global_market_universe(cfg: dict | None = None) -> dict[str, dict]:
    cfg = cfg or load_config()
    raw = (load_global_desk_config(cfg).get("markets") or {}).copy()
    markets: dict[str, dict] = {k: dict(v) for k, v in raw.items()}
    if "us" in markets:
        base = markets["us"].get("tickers") or []
        markets["us"]["tickers"] = sorted(set(base + load_nyse_tickers(cfg)))
    return markets


def crypto_tier_universe(cfg: dict | None = None) -> dict[str, dict]:
    return (load_global_desk_config(cfg).get("crypto_tiers") or {})
