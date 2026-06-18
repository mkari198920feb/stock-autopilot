from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.symbol_normalize import to_yahoo_symbol

_SCAN_TTL = 900  # 15 min for pulse movers


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def scan_symbol_pulse(symbol: str) -> dict | None:
    symbol = to_yahoo_symbol(symbol)
    cache_key = f"pulse_scan:{symbol}"
    hit = cache_get_json(cache_key)
    if isinstance(hit, dict) and hit.get("symbol"):
        return hit

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y", auto_adjust=True)
        if hist.empty or len(hist) < 5:
            return None

        info = ticker.info or {}
        closes = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()
        price = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else price
        change_abs = price - prev
        change_pct = (change_abs / prev * 100) if prev else 0.0

        w52_high = float(closes.max())
        w52_low = float(closes.min())
        ath = float(closes.max())
        avg_vol = float(volumes.tail(20).mean()) if len(volumes) >= 5 else float(volumes.iloc[-1])
        today_vol = float(volumes.iloc[-1])
        vol_vs_avg = (today_vol / avg_vol * 100) if avg_vol > 0 else 100.0

        near_52_high = price >= w52_high * 0.99
        near_52_low = price <= w52_low * 1.01
        near_ath = price >= ath * 0.995

        is_india = symbol.upper().endswith(".NS") or symbol.upper().endswith(".BO")
        upper_circuit = is_india and change_pct >= 4.5
        lower_circuit = is_india and change_pct <= -4.5

        row = {
            "symbol": symbol,
            "name": info.get("shortName") or info.get("longName") or symbol,
            "cmp": round(price, 4),
            "change_abs": round(change_abs, 4),
            "change_pct": round(change_pct, 2),
            "volume_vs_avg_pct": round(vol_vs_avg, 1),
            "sector": info.get("sector") or "Unknown",
            "industry": info.get("industry") or info.get("sector") or "Unknown",
            "week_52_high": round(w52_high, 4),
            "week_52_low": round(w52_low, 4),
            "near_52_high": near_52_high,
            "near_52_low": near_52_low,
            "near_ath": near_ath,
            "upper_circuit": upper_circuit,
            "lower_circuit": lower_circuit,
            "currency": info.get("currency") or ("INR" if is_india else "USD"),
        }
        cache_set_json(cache_key, row, _SCAN_TTL)
        return row
    except Exception:
        return None


def batch_scan_pulse(symbols: list[str], max_workers: int = 10) -> list[dict]:
    if not symbols:
        return []
    out: list[dict] = []

    def _one(sym: str) -> dict | None:
        return scan_symbol_pulse(sym)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(symbols))) as pool:
        futures = {pool.submit(_one, s): s for s in symbols}
        for fut in as_completed(futures):
            row = fut.result()
            if row:
                out.append(row)
    return out


def scan_index_quote(symbol: str, label: str) -> dict | None:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        val = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else val
        chg = val - prev
        pct = (chg / prev * 100) if prev else 0.0
        direction = "up" if pct > 0.05 else "down" if pct < -0.05 else "flat"
        return {
            "label": label,
            "symbol": symbol,
            "value": round(val, 2),
            "change_abs": round(chg, 2),
            "change_pct": round(pct, 2),
            "direction": direction,
        }
    except Exception:
        return None
