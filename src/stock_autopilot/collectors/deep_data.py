from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.symbol_normalize import to_yahoo_symbol
from stock_autopilot.collectors.market import _macd_hist, _rsi

_DEEP_TTL = 3600


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b) * 100


def _series_last(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[0]
    return _safe_float(val)


def _quarterly_revenue(financials: pd.DataFrame | None) -> list[dict]:
    if financials is None or financials.empty:
        return []
    row = None
    for label in ("Total Revenue", "Revenue"):
        if label in financials.index:
            row = financials.loc[label]
            break
    if row is None:
        return []
    out = []
    for col in row.index[:4]:
        val = _safe_float(row[col])
        if val is not None:
            out.append({"period": str(col.date()) if hasattr(col, "date") else str(col), "revenue": val})
    return out


def fetch_deep_bundle(symbol: str) -> dict | None:
    sym = to_yahoo_symbol(symbol)
    cache_key = f"deep:{sym}"
    hit = cache_get_json(cache_key)
    if isinstance(hit, dict) and hit.get("symbol"):
        return hit

    try:
        ticker = yf.Ticker(sym)
        info = ticker.info or {}
        hist = ticker.history(period="2y", auto_adjust=True)
        if hist.empty or len(hist) < 60:
            return None

        closes = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()
        price = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else price
        change_abs = price - prev_close
        change_pct = (change_abs / prev_close * 100) if prev_close else 0.0

        ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
        ma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
        ma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
        w52_high = float(closes.tail(252).max()) if len(closes) >= 60 else float(closes.max())
        w52_low = float(closes.tail(252).min()) if len(closes) >= 60 else float(closes.min())
        ath = float(closes.max())

        avg_vol = float(volumes.tail(20).mean()) if len(volumes) >= 5 else 0.0
        today_vol = float(volumes.iloc[-1])
        vol_vs_avg = (today_vol / avg_vol * 100) if avg_vol > 0 else 100.0

        rsi = _rsi(closes)
        macd_hist = _macd_hist(closes)

        ma200_slope = None
        if ma200 and len(closes) >= 220:
            ma200_prev = float(closes.tail(200).head(180).mean())
            ma200_slope = "Rising" if ma200 > ma200_prev * 1.01 else "Falling" if ma200 < ma200_prev * 0.99 else "Flat"

        financials = getattr(ticker, "financials", None)
        balance = getattr(ticker, "balance_sheet", None)
        cashflow = getattr(ticker, "cashflow", None)
        recommendations = getattr(ticker, "recommendations", None)

        rev_q = _quarterly_revenue(financials)
        rev_yoy = _safe_float(info.get("revenueGrowth"))
        gross_margin = _safe_float(info.get("grossMargins"))
        op_margin = _safe_float(info.get("operatingMargins"))
        profit_margin = _safe_float(info.get("profitMargins"))
        roe = _safe_float(info.get("returnOnEquity"))
        roa = _safe_float(info.get("returnOnAssets"))
        debt_equity = _safe_float(info.get("debtToEquity"))
        current_ratio = _safe_float(info.get("currentRatio"))
        quick_ratio = _safe_float(info.get("quickRatio"))
        total_cash = _safe_float(info.get("totalCash"))
        total_debt = _safe_float(info.get("totalDebt"))
        book_value = _safe_float(info.get("bookValue"))
        fcf = _safe_float(info.get("freeCashflow"))
        mcap = _safe_float(info.get("marketCap"))
        fcf_yield = (fcf / mcap * 100) if fcf and mcap and mcap > 0 else None
        div_yield = _safe_float(info.get("dividendYield"))
        if div_yield and div_yield < 1:
            div_yield *= 100

        analyst = {
            "buy": int(info.get("recommendationMean") and 0 or 0),
            "target_mean": _safe_float(info.get("targetMeanPrice")),
            "target_high": _safe_float(info.get("targetHighPrice")),
            "target_low": _safe_float(info.get("targetLowPrice")),
            "num_analysts": int(info.get("numberOfAnalystOpinions") or 0),
        }
        rec_key = info.get("recommendationKey", "")
        if recommendations is not None and not recommendations.empty:
            recent = recommendations.tail(20)
            analyst["recent_actions"] = recent.reset_index().to_dict(orient="records")[:5]

        is_india = sym.endswith(".NS") or sym.endswith(".BO")
        currency = info.get("currency") or ("INR" if is_india else "USD")
        exchange = info.get("exchange") or ("NSE" if sym.endswith(".NS") else "BSE" if sym.endswith(".BO") else info.get("fullExchangeName") or "—")

        bundle = {
            "symbol": sym,
            "name": info.get("longName") or info.get("shortName") or sym,
            "exchange": exchange,
            "sector": info.get("sector") or "Unknown",
            "industry": info.get("industry") or info.get("sector") or "Unknown",
            "currency": currency,
            "cmp": price,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "week_52_high": w52_high,
            "week_52_low": w52_low,
            "all_time_high": ath,
            "week_52_high_dist_pct": (w52_high - price) / w52_high * 100 if w52_high else 0,
            "week_52_low_dist_pct": (price - w52_low) / w52_low * 100 if w52_low else 0,
            "market_cap": mcap,
            "summary": info.get("longBusinessSummary") or info.get("description") or "",
            "website": info.get("website"),
            "employees": info.get("fullTimeEmployees"),
            "beta": _safe_float(info.get("beta")),
            "pe_trailing": _safe_float(info.get("trailingPE")),
            "pe_forward": _safe_float(info.get("forwardPE")),
            "pb": _safe_float(info.get("priceToBook")),
            "ps": _safe_float(info.get("priceToSalesTrailing12Months")),
            "ev_ebitda": _safe_float(info.get("enterpriseToEbitda")),
            "peg": _safe_float(info.get("pegRatio")),
            "fcf_yield": fcf_yield,
            "div_yield": div_yield,
            "revenue_growth_yoy": rev_yoy,
            "gross_margin": gross_margin,
            "operating_margin": op_margin,
            "profit_margin": profit_margin,
            "roe": roe * 100 if roe and roe < 2 else roe,
            "roa": roa * 100 if roa and roa < 2 else roa,
            "debt_equity": debt_equity,
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
            "total_cash": total_cash,
            "total_debt": total_debt,
            "net_debt": (total_debt - total_cash) if total_debt is not None and total_cash is not None else None,
            "book_value": book_value,
            "fcf": fcf,
            "eps_ttm": _safe_float(info.get("trailingEps")),
            "revenue_quarters": rev_q,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "ma200_slope": ma200_slope,
            "rsi": rsi,
            "macd_hist": macd_hist,
            "avg_volume_20d": avg_vol,
            "volume_vs_avg_pct": vol_vs_avg,
            "support": float(closes.tail(60).min()) if len(closes) >= 20 else None,
            "resistance": float(closes.tail(60).max()) if len(closes) >= 20 else None,
            "momentum_3m": float(closes.iloc[-1] / closes.iloc[-63] - 1) if len(closes) >= 63 else 0,
            "analyst": analyst,
            "recommendation_key": rec_key,
            "held_percent_insiders": _safe_float(info.get("heldPercentInsiders")),
            "held_percent_institutions": _safe_float(info.get("heldPercentInstitutions")),
            "short_ratio": _safe_float(info.get("shortRatio")),
        }
        cache_set_json(cache_key, bundle, _DEEP_TTL)
        return bundle
    except Exception:
        return None
