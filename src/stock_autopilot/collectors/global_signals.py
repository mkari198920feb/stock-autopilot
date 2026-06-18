from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from stock_autopilot.collectors.macro import analyze_global_conditions


def _pct(symbol: str, period: str = "1mo") -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if len(hist) < 2:
            return None
        return round(float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2)
    except Exception:
        return None


def _last(symbol: str) -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def build_global_signal_stack(cfg: dict) -> dict:
    macro_syms = cfg.get("macro_symbols", {})
    macro = analyze_global_conditions(macro_syms)

    sp_trend = "Bull" if (macro.indicators.get("sp500_1m_pct") or 0) > 0 else "Bear"
    vix = macro.indicators.get("vix")
    risk_sentiment = "Risk-on" if vix and vix < 20 else "Risk-off" if vix and vix > 25 else "Neutral"

    stack = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "us_markets": {
            "sp500_trend": sp_trend,
            "vix": vix,
            "us_10y": macro.indicators.get("us_10y_yield"),
            "risk_sentiment": risk_sentiment,
        },
        "global_risk": {
            "regime": macro.regime,
            "risk_score": macro.risk_score,
            "msci_em_1m_pct": macro.indicators.get("emerging_1m_pct"),
            "copper_proxy": _pct("HG=F"),
            "oil_brent_pct": macro.indicators.get("oil_1m_pct"),
            "gold_pct": macro.indicators.get("gold_1m_pct"),
        },
        "regional_central_banks": {
            "fed_note": "See US 10Y — next FOMC on calendar",
            "ecb_note": "ECB — watch EUR inflation path",
            "boj_note": "BOJ — YCC ended, yen volatility elevated",
            "rbi_repo": cfg.get("india_desk", {}).get("macro", {}).get("repo_rate", 6.5),
        },
        "currencies": {
            "dxy_level": _last(macro_syms.get("usd_index", "DX-Y.NYB")),
            "eurusd_note": "EUR/USD — ECB vs Fed divergence",
            "usdjpy_note": "USD/JPY — carry trade sensitivity",
        },
        "commodities": {
            "gold": _last(macro_syms.get("gold", "GC=F")),
            "brent": _last("BZ=F"),
            "wti": _last(macro_syms.get("oil", "CL=F")),
            "copper": _last("HG=F"),
        },
        "summary": macro.summary,
    }
    return stack


def build_macro_ticker(cfg: dict, india_macro: dict | None = None, btc_price: float | None = None) -> list[dict]:
    """Scrolling dashboard ticker items."""
    syms = cfg.get("macro_symbols", {})
    items: list[dict] = []

    def add(label: str, sym: str, fmt: str = "{:,.2f}", pct_sym: str | None = None):
        val = _last(sym)
        if val is None:
            return
        chg = _pct(pct_sym or sym, "5d")
        items.append({
            "label": label,
            "value": fmt.format(val),
            "change": f"{chg:+.2f}%" if chg is not None else "",
            "up": chg is not None and chg > 0,
        })

    add("S&P 500", syms.get("sp500", "^GSPC"))
    add("Nasdaq", syms.get("nasdaq", "^IXIC"))
    add("DAX", "^GDAXI")
    add("Nikkei", syms.get("japan", "^N225"))
    if india_macro:
        items.append({
            "label": "Nifty 50",
            "value": f"{india_macro.get('nifty', 0):,.0f}",
            "change": f"{india_macro.get('nifty_change_pct', 0):+.2f}%",
            "up": (india_macro.get("nifty_change_pct") or 0) > 0,
        })
    if btc_price:
        items.append({
            "label": "Bitcoin",
            "value": f"${btc_price:,.0f}",
            "change": "",
            "up": True,
        })
    add("Gold", syms.get("gold", "GC=F"), "${:,.0f}")
    add("Oil", syms.get("oil", "CL=F"), "${:,.2f}")
    dxy = _last(syms.get("usd_index", "DX-Y.NYB"))
    if dxy:
        items.append({"label": "DXY", "value": f"{dxy:.2f}", "change": "", "up": False})
    return items
