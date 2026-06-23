from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from stock_autopilot.models.schemas import IndiaMacroBar


def _latest(symbol: str) -> tuple[float | None, float | None]:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if len(hist) < 2:
            return None, None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None, None
        last = float(closes.iloc[-1])
        chg = float(closes.iloc[-1] / closes.iloc[-2] - 1) * 100
        return last, chg
    except Exception:
        return None, None


def _level(symbol: str) -> float | None:
    v, _ = _latest(symbol)
    return v


def fetch_india_macro(cfg: dict) -> IndiaMacroBar:
    india_cfg = cfg.get("india_desk", {})
    macro_cfg = india_cfg.get("macro", {})

    nifty, nifty_chg = _latest("^NSEI")
    sensex, sensex_chg = _latest("^BSESN")
    vix, _ = _latest("^INDIAVIX")
    inr, inr_chg = _latest("USDINR=X")
    brent, _ = _latest("BZ=F")

    repo = float(macro_cfg.get("repo_rate", 6.50))
    stance = macro_cfg.get("rbi_stance", "Neutral")

    vix_sent = "Neutral"
    if vix:
        if vix > 20:
            vix_sent = "Fear"
        elif vix < 13:
            vix_sent = "Complacent"

    brent_impact = "Neutral"
    if brent:
        if brent > 85:
            brent_impact = "Bearish for India (inflation/CAD)"
        elif brent < 70:
            brent_impact = "Bullish for India (OMCs/FMCG)"

    nifty_pe = None
    pe_assessment = "Fair"
    try:
        pe_hist = yf.Ticker("^NSEI").info
        nifty_pe = pe_hist.get("trailingPE")
        if nifty_pe and nifty_pe > 24:
            pe_assessment = "Expensive"
        elif nifty_pe and nifty_pe < 18:
            pe_assessment = "Cheap"
    except Exception:
        pass

    nifty = nifty or 0.0
    sensex = sensex or 0.0
    vix_str = f"{vix:.1f}" if vix else "—"
    inr_str = f"₹{inr:.2f}" if inr else "—"
    brent_str = f"${brent:.0f}" if brent else "—"
    ticker = (
        f"Nifty: {nifty:,.0f} ({nifty_chg:+.2f}%) | Sensex: {sensex:,.0f} ({sensex_chg:+.2f}%) | "
        f"VIX: {vix_str} | Repo: {repo:.2f}% | INR: {inr_str} | Brent: {brent_str}"
    )

    return IndiaMacroBar(
        nifty=nifty,
        nifty_change_pct=round(nifty_chg or 0, 2),
        sensex=sensex,
        sensex_change_pct=round(sensex_chg or 0, 2),
        india_vix=round(vix, 2) if vix else None,
        vix_sentiment=vix_sent,
        inr_usd=round(inr, 2) if inr else None,
        inr_change_pct=round(inr_chg, 2) if inr_chg else None,
        brent_usd=round(brent, 2) if brent else None,
        brent_impact=brent_impact,
        repo_rate=repo,
        rbi_stance=stance,
        repo_rate_source="config",
        market_data_as_of=datetime.now(timezone.utc),
        nifty_pe=round(nifty_pe, 1) if nifty_pe else None,
        pe_assessment=pe_assessment,
        ticker_text=ticker,
    )
