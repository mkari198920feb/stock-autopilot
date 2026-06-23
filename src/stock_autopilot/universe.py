from __future__ import annotations

from pathlib import Path

import yaml

from stock_autopilot.config import settings

DEFAULT_US_FILE = "data/universe/us_equities.txt"


def load_config() -> dict:
    with open(settings.config_path) as f:
        return yaml.safe_load(f)


def _resolve_path(rel: str | Path) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = settings.project_root / p
    return p


def load_ticker_file(path: str | Path) -> list[str]:
    """YAML (`tickers:` list) or plain text — one Yahoo symbol per line."""
    p = _resolve_path(path)
    if not p.exists():
        return []
    if p.suffix.lower() in {".txt", ".csv"}:
        tickers: list[str] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tickers.append(line.upper())
        return sorted(set(tickers))
    with open(p) as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, list):
        return sorted({str(s).strip().upper() for s in data if str(s).strip()})
    return sorted({str(s).strip().upper() for s in (data.get("tickers") or []) if str(s).strip()})


def us_equities_file(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    uni = cfg.get("universe") or {}
    return uni.get("us_equities_file") or uni.get("nyse_file") or DEFAULT_US_FILE


def load_us_equities(cfg: dict | None = None) -> list[str]:
    return load_ticker_file(us_equities_file(cfg))


def north_america_tickers(cfg: dict | None = None) -> list[str]:
    """US common equities file plus any extras under regions.north_america."""
    cfg = cfg or load_config()
    extras = [s.strip().upper() for s in (cfg.get("regions") or {}).get("north_america") or [] if s.strip()]
    return sorted(set(load_us_equities(cfg) + extras))


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


def all_tickers(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    tickers: list[str] = []
    for region, symbols in (cfg.get("regions") or {}).items():
        if region == "north_america":
            tickers.extend(north_america_tickers(cfg))
        elif isinstance(symbols, list):
            tickers.extend(symbols)
    gd = load_global_desk_config(cfg)
    for market in (gd.get("markets") or {}).values():
        tickers.extend(_market_tickers(market, cfg))
    return sorted(set(tickers))


def _market_tickers(market_cfg: dict, cfg: dict) -> list[str]:
    if market_cfg.get("use_us_equities_file"):
        return load_us_equities(cfg)
    if market_cfg.get("tickers_file"):
        return load_ticker_file(market_cfg["tickers_file"])
    return list(market_cfg.get("tickers") or [])


def ticker_region_map(cfg: dict | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    mapping: dict[str, str] = {}
    for region, symbols in (cfg.get("regions") or {}).items():
        label = region.replace("_", " ").title()
        if region == "north_america":
            for sym in north_america_tickers(cfg):
                mapping[sym] = label
        elif isinstance(symbols, list):
            for sym in symbols:
                mapping[sym] = label
    gd = load_global_desk_config(cfg)
    for market_id, market in (gd.get("markets") or {}).items():
        label = market.get("label", market_id)
        for sym in _market_tickers(market, cfg):
            mapping[sym] = label
    return mapping


def global_market_universe(cfg: dict | None = None) -> dict[str, dict]:
    cfg = cfg or load_config()
    raw = (load_global_desk_config(cfg).get("markets") or {}).copy()
    markets: dict[str, dict] = {k: dict(v) for k, v in raw.items()}
    if markets.get("us", {}).get("use_us_equities_file"):
        markets["us"] = {**markets["us"], "tickers": load_us_equities(cfg)}
    return markets


def crypto_tier_universe(cfg: dict | None = None) -> dict[str, dict]:
    return (load_global_desk_config(cfg).get("crypto_tiers") or {})


# Back-compat alias used in tests
load_nyse_tickers = load_us_equities
