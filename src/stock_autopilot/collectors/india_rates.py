from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json

GSEC_SYMBOLS = ("IN10YT=RR", "^TNX")
GOLD_SYMBOLS = ("GOLDBEES.NS", "GC=F")
_CACHE_KEY = "india:rates"
_CACHE_TTL = 3600


def _last_close(symbol: str) -> tuple[float | None, str | None]:
    try:
        hist = yf.Ticker(symbol).history(period="1mo", auto_adjust=True)
        if hist.empty:
            return None, None
        price = float(hist["Close"].iloc[-1])
        as_of = hist.index[-1].strftime("%Y-%m-%d")
        return price, as_of
    except Exception:
        return None, None


def _month_change(symbol: str) -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period="3mo", auto_adjust=True)
        if len(hist) < 22:
            return None
        closes = hist["Close"].dropna()
        ref = float(closes.iloc[-22])
        last = float(closes.iloc[-1])
        if ref <= 0:
            return None
        return round((last / ref - 1) * 100, 2)
    except Exception:
        return None


def fetch_india_market_rates(*, force: bool = False, ttl: int = _CACHE_TTL) -> dict:
    if not force and ttl > 0:
        hit = cache_get_json(_CACHE_KEY)
        if isinstance(hit, dict) and hit.get("gsec_yield_pct") is not None:
            return hit

    gsec_yield, gsec_as_of, gsec_sym = None, None, None
    for sym in GSEC_SYMBOLS:
        val, as_of = _last_close(sym)
        if val is not None:
            gsec_yield, gsec_as_of, gsec_sym = round(val, 2), as_of, sym
            break

    gold_chg, gold_sym = None, None
    for sym in GOLD_SYMBOLS:
        chg = _month_change(sym)
        if chg is not None:
            gold_chg, gold_sym = chg, sym
            break

    result = {
        "gsec_yield_pct": gsec_yield,
        "gsec_as_of": gsec_as_of,
        "gsec_symbol": gsec_sym,
        "gold_1m_pct": gold_chg,
        "gold_symbol": gold_sym,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if ttl > 0 and (gsec_yield is not None or gold_chg is not None):
        cache_set_json(_CACHE_KEY, result, ttl)
    return result
