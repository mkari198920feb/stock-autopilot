from __future__ import annotations

from dataclasses import dataclass

import yfinance as yf

from stock_autopilot.collectors.coingecko import symbol_to_id, fetch_simple_prices
from stock_autopilot.universe import crypto_tier_universe, global_market_universe, load_config


@dataclass
class TickerValidation:
    symbol: str
    source: str
    ok: bool
    reason: str


def _validate_equity(symbol: str) -> tuple[bool, str]:
    try:
        hist = yf.Ticker(symbol).history(period="10d", auto_adjust=True)
        if hist.empty or len(hist) < 3:
            return False, "no price history"
        price = float(hist["Close"].iloc[-1])
        if price <= 0:
            return False, "invalid price"
        return True, "ok"
    except Exception as e:
        return False, str(e)[:80]


def _validate_crypto(symbol: str, coingecko_id: str | None = None) -> tuple[bool, str]:
    cid = coingecko_id or symbol_to_id(symbol.replace("-USD", ""))
    if cid:
        data = fetch_simple_prices([cid], ttl=60)
        if data.get(cid, {}).get("usd"):
            return True, "coingecko ok"
    sym = symbol if "-USD" in symbol else f"{symbol}-USD"
    try:
        hist = yf.Ticker(sym).history(period="5d", auto_adjust=True)
        if not hist.empty:
            return True, "yahoo ok"
    except Exception:
        pass
    return False, "no crypto data"


def collect_all_symbols(sources: list[str] | None = None) -> list[tuple[str, str]]:
    cfg = load_config()
    sources = sources or ["regions", "india", "global", "crypto"]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(sym: str, src: str) -> None:
        if sym and sym not in seen:
            seen.add(sym)
            out.append((sym, src))

    if "regions" in sources:
        for region, syms in cfg.get("regions", {}).items():
            for s in syms:
                add(s, f"regions.{region}")

    if "india" in sources:
        for s in cfg.get("india_desk", {}).get("nse_universe") or []:
            add(s, "india_desk.nse")

    if "global" in sources:
        for mid, mcfg in global_market_universe(cfg).items():
            for s in mcfg.get("tickers") or []:
                add(s, f"global.{mid}")

    if "crypto" in sources:
        for cat_id, cat in crypto_tier_universe(cfg).items():
            for entry in cat.get("symbols") or []:
                if isinstance(entry, dict):
                    t = entry.get("ticker", "").replace("-USD", "")
                    add(t, f"crypto.{cat_id}")
                else:
                    add(str(entry).replace("-USD", ""), f"crypto.{cat_id}")

    return out


def validate_universe(sources: list[str] | None = None) -> list[TickerValidation]:
    results: list[TickerValidation] = []
    for sym, src in collect_all_symbols(sources):
        if src.startswith("crypto."):
            ok, reason = _validate_crypto(sym)
        else:
            ok, reason = _validate_equity(sym)
        results.append(TickerValidation(symbol=sym, source=src, ok=ok, reason=reason))
    return results


def invalid_symbols(sources: list[str] | None = None) -> list[TickerValidation]:
    return [r for r in validate_universe(sources) if not r.ok]
