from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from stock_autopilot.models.schemas import MacroSnapshot


def _pct_change(symbol: str, period: str = "1mo") -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if len(hist) < 2:
            return None
        return float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1)
    except Exception:
        return None


def _latest_level(symbol: str) -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def analyze_global_conditions(macro_symbols: dict[str, str]) -> MacroSnapshot:
    indicators: dict[str, float | str | None] = {}

    sp_chg = _pct_change(macro_symbols.get("sp500", "^GSPC"))
    vix = _latest_level(macro_symbols.get("vix", "^VIX"))
    oil_chg = _pct_change(macro_symbols.get("oil", "CL=F"))
    gold_chg = _pct_change(macro_symbols.get("gold", "GC=F"))
    em_chg = _pct_change(macro_symbols.get("emerging", "EEM"))
    rates = _latest_level(macro_symbols.get("us_10y", "^TNX"))

    for key, sym in macro_symbols.items():
        chg = _pct_change(sym, "1mo")
        if chg is not None:
            indicators[f"{key}_1m_pct"] = round(chg * 100, 2)

    if vix is not None:
        indicators["vix"] = round(vix, 2)

    if rates is not None:
        indicators["us_10y_yield"] = round(rates, 2)

    risk_score = 0.5
    notes: list[str] = []

    if vix is not None:
        if vix > 25:
            risk_score += 0.2
            notes.append(f"Elevated fear (VIX {vix:.1f}) — favor quality and defensives.")
        elif vix < 15:
            risk_score -= 0.1
            notes.append(f"Low volatility (VIX {vix:.1f}) — risk appetite supported.")

    if sp_chg is not None:
        if sp_chg < -0.05:
            risk_score += 0.15
            notes.append(f"S&P 500 down {sp_chg*100:.1f}% over 1M — cautious positioning.")
        elif sp_chg > 0.03:
            risk_score -= 0.1
            notes.append(f"S&P 500 up {sp_chg*100:.1f}% over 1M — momentum supportive.")

    if em_chg is not None and sp_chg is not None:
        if em_chg > sp_chg + 0.02:
            notes.append("Emerging markets outperforming — global risk-on breadth.")
        elif em_chg < sp_chg - 0.03:
            notes.append("EM lagging — selective international exposure.")

    if gold_chg is not None and gold_chg > 0.05:
        notes.append("Gold strong — hedging demand or uncertainty elevated.")

    if oil_chg is not None and abs(oil_chg) > 0.08:
        notes.append(f"Energy shock (oil {oil_chg*100:+.1f}% 1M) — watch input costs and inflation.")

    risk_score = max(0.0, min(1.0, risk_score))
    if risk_score >= 0.65:
        regime = "Risk-Off / Defensive"
    elif risk_score <= 0.35:
        regime = "Risk-On / Growth"
    else:
        regime = "Neutral / Balanced"

    summary = " ".join(notes) if notes else "Global conditions mixed; balanced diversification recommended."

    return MacroSnapshot(
        captured_at=datetime.now(timezone.utc),
        regime=regime,
        risk_score=round(risk_score, 2),
        summary=summary,
        indicators={k: v for k, v in indicators.items() if v is not None},
    )
