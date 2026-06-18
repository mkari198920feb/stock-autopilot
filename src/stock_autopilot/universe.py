from __future__ import annotations

from pathlib import Path

import yaml

from stock_autopilot.config import settings


def load_config() -> dict:
    with open(settings.config_path) as f:
        return yaml.safe_load(f)


def load_global_desk_config(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    gd = cfg.get("global_desk", {})
    path = gd.get("markets_file")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = settings.project_root / p
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


def all_tickers(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    tickers: list[str] = []
    for symbols in cfg.get("regions", {}).values():
        tickers.extend(symbols)
    gd = load_global_desk_config(cfg)
    for market in (gd.get("markets") or {}).values():
        tickers.extend(market.get("tickers") or [])
    return sorted(set(tickers))


def ticker_region_map(cfg: dict | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    mapping: dict[str, str] = {}
    for region, symbols in cfg.get("regions", {}).items():
        for sym in symbols:
            mapping[sym] = region.replace("_", " ").title()
    gd = load_global_desk_config(cfg)
    for market_id, market in (gd.get("markets") or {}).items():
        label = market.get("label", market_id)
        for sym in market.get("tickers") or []:
            mapping[sym] = label
    return mapping


def global_market_universe(cfg: dict | None = None) -> dict[str, dict]:
    return (load_global_desk_config(cfg).get("markets") or {})


def crypto_tier_universe(cfg: dict | None = None) -> dict[str, dict]:
    return (load_global_desk_config(cfg).get("crypto_tiers") or {})
