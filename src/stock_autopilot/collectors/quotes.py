from __future__ import annotations

import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.coingecko import fetch_simple_prices, symbol_to_id
from stock_autopilot.collectors.symbol_normalize import to_yahoo_symbol


def _from_fast_info(ticker: yf.Ticker) -> float | None:
    try:
        fi = ticker.fast_info
        for attr in ("last_price", "lastPrice", "regular_market_price", "regularMarketPrice"):
            val = getattr(fi, attr, None)
            if val is None and hasattr(fi, "get"):
                val = fi.get(attr)
            if val is not None:
                p = float(val)
                if p > 0:
                    return p
    except Exception:
        pass
    return None


def _from_history(ticker: yf.Ticker) -> float | None:
    try:
        hist = ticker.history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        p = float(hist["Close"].iloc[-1])
        return p if p > 0 else None
    except Exception:
        return None


def fetch_quote(symbol: str) -> float | None:
    sym = to_yahoo_symbol(symbol.strip())
    if not sym:
        return None

    asset = sym.replace("-USD", "")
    if sym in ("BTC", "ETH") or sym.endswith("-USD") or sym.endswith("USDT"):
        coin_id = symbol_to_id(asset)
        if coin_id:
            row = fetch_simple_prices([coin_id], ttl=90).get(coin_id) or {}
            if row.get("usd"):
                return float(row["usd"])
        if sym in ("BTC", "ETH"):
            ysym = f"{asset}-USD"
            ticker = yf.Ticker(ysym)
            return _from_fast_info(ticker) or _from_history(ticker)

    ysym = sym if "." in sym or sym.endswith("-USD") else sym
    ticker = yf.Ticker(ysym)
    return _from_fast_info(ticker) or _from_history(ticker)


def batch_fetch_quotes(symbols: list[str], ttl: int = 90) -> dict[str, float]:
    """Fetch latest prices for many symbols; uses short TTL cache."""
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return {}

    cache_key = "quotes:" + ",".join(sorted(unique))
    hit = cache_get_json(cache_key)
    if isinstance(hit, dict):
        return {k: float(v) for k, v in hit.items() if v}

    out: dict[str, float] = {}
    crypto_ids: dict[str, str] = {}
    yahoo_syms: list[str] = []
    sym_lookup: dict[str, str] = {}

    for sym in unique:
        ysym = to_yahoo_symbol(sym)
        sym_lookup[ysym] = sym
        asset = ysym.replace("-USD", "")
        if ysym in ("BTC", "ETH") or ysym.endswith("-USD"):
            cid = symbol_to_id(asset)
            if cid:
                crypto_ids[sym] = cid
                continue
        yahoo_syms.append(ysym)

    if crypto_ids:
        prices = fetch_simple_prices(list(set(crypto_ids.values())), ttl=ttl)
        id_to_sym = {v: k for k, v in crypto_ids.items()}
        for cid, row in prices.items():
            sym = id_to_sym.get(cid)
            if sym and row.get("usd"):
                out[sym] = float(row["usd"])
        for sym, cid in crypto_ids.items():
            if sym not in out:
                p = fetch_quote(sym)
                if p:
                    out[sym] = p

    if yahoo_syms:
        try:
            tickers = yf.Tickers(" ".join(yahoo_syms))
            for sym in yahoo_syms:
                t = tickers.tickers.get(sym)
                if not t:
                    t = yf.Ticker(sym)
                p = _from_fast_info(t) or _from_history(t)
                if p:
                    out[sym_lookup.get(sym, sym)] = p
        except Exception:
            for sym in yahoo_syms:
                p = fetch_quote(sym_lookup.get(sym, sym))
                if p:
                    out[sym_lookup.get(sym, sym)] = p

    if out:
        cache_set_json(cache_key, out, ttl)
    return out
