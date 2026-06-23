from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.symbol_normalize import to_yahoo_symbol
from stock_autopilot.models.schemas import StockMetrics

_CACHE_TTL = 3600  # 1h for daily equity metrics


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else 50.0


def _macd_hist(closes: pd.Series) -> float | None:
    if len(closes) < 35:
        return None
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    val = hist.iloc[-1]
    return float(val) if pd.notna(val) else None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _fetch_stock_metrics_uncached(
    symbol: str,
    region: str,
    lookback_days: int = 252,
) -> StockMetrics | None:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{lookback_days + 30}d", auto_adjust=True)
        if hist.empty or len(hist) < 60:
            return None

        info = ticker.info or {}
        closes = hist["Close"].dropna()
        if len(closes) < 60:
            return None
        returns = closes.pct_change().dropna()
        if len(returns) < 30:
            return None

        price = float(closes.iloc[-1])
        if np.isnan(price) or price <= 0:
            return None
        ann_return = float((closes.iloc[-1] / closes.iloc[0]) ** (252 / len(closes)) - 1)
        vol = float(returns.std() * np.sqrt(252))
        sharpe = float(ann_return / vol) if vol > 0 else 0.0
        rsi = _rsi(closes)

        avg_vol = float(hist["Volume"].tail(20).mean())

        mom_3m = float(closes.iloc[-1] / closes.iloc[-63] - 1) if len(closes) >= 63 else 0.0
        mom_12m = float(closes.iloc[-1] / closes.iloc[0] - 1)

        pe = info.get("trailingPE") or info.get("forwardPE")
        pe_ratio = _safe_float(pe)
        if pe_ratio is not None and pe_ratio <= 0:
            pe_ratio = None

        ma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
        ma_200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
        window = closes.tail(60)
        support = float(window.min()) if len(window) >= 20 else None
        resistance = float(window.max()) if len(window) >= 20 else None

        mcap = _safe_float(info.get("marketCap"))
        fcf = _safe_float(info.get("freeCashflow"))
        fcf_yield = (fcf / mcap) if fcf and mcap and mcap > 0 else None

        return StockMetrics(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName") or symbol,
            region=region,
            sector=info.get("sector") or "Unknown",
            industry=info.get("industry") or info.get("sector") or "Unknown",
            price=price,
            annualized_return=ann_return,
            volatility=vol,
            sharpe=sharpe,
            rsi=rsi,
            pe_ratio=pe_ratio,
            pe_forward=_safe_float(info.get("forwardPE")),
            avg_volume=avg_vol,
            momentum_3m=mom_3m,
            momentum_12m=mom_12m,
            beta=_safe_float(info.get("beta")),
            ma_50=ma_50,
            ma_200=ma_200,
            macd_hist=_macd_hist(closes),
            support=support,
            resistance=resistance,
            revenue_growth_yoy=_safe_float(info.get("revenueGrowth")),
            gross_margin=_safe_float(info.get("grossMargins")),
            operating_margin=_safe_float(info.get("operatingMargins")),
            ev_ebitda=_safe_float(info.get("enterpriseToEbitda")),
            peg_ratio=_safe_float(info.get("pegRatio")),
            fcf_yield=fcf_yield,
            debt_to_equity=_safe_float(info.get("debtToEquity")),
            roe=_safe_float(info.get("returnOnEquity")),
            roic=_safe_float(info.get("returnOnAssets")),
        )
    except Exception:
        return None


def fetch_stock_metrics(
    symbol: str,
    region: str,
    lookback_days: int = 252,
) -> StockMetrics | None:
    symbol = to_yahoo_symbol(symbol)
    cache_key = f"metrics:{symbol}:{lookback_days}"
    hit = cache_get_json(cache_key)
    if isinstance(hit, dict):
        try:
            return StockMetrics(**hit)
        except Exception:
            pass
    m = _fetch_stock_metrics_uncached(symbol, region, lookback_days)
    if m:
        cache_set_json(cache_key, m.model_dump(), _CACHE_TTL)
    return m


def batch_fetch_metrics(
    symbols: list[str],
    region_map: dict[str, str],
    lookback_days: int = 252,
    max_workers: int = 8,
    batch_size: int = 0,
) -> list[StockMetrics]:
    results: list[StockMetrics] = []
    if not symbols:
        return results

    chunk_size = batch_size if batch_size > 0 else len(symbols)
    workers = min(max_workers, max(1, chunk_size))

    def _one(sym: str) -> StockMetrics | None:
        return fetch_stock_metrics(sym, region_map.get(sym, "Global"), lookback_days)

    for start in range(0, len(symbols), chunk_size):
        chunk = symbols[start : start + chunk_size]
        with ThreadPoolExecutor(max_workers=min(workers, len(chunk))) as pool:
            futures = {pool.submit(_one, sym): sym for sym in chunk}
            for fut in as_completed(futures):
                m = fut.result()
                if m:
                    results.append(m)
    return results
