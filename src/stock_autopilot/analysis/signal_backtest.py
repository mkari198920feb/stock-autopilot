from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from stock_autopilot.db import get_outcome_stats
from stock_autopilot.universe import load_config

DEFAULT_BACKTEST_SYMBOLS = ("SPY", "^NSEI", "BTC-USD")


def _rsi_series(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def backtest_rsi_reversal(
    symbol: str,
    *,
    period: str = "2y",
    rsi_buy: float = 30.0,
    hold_days: int = 7,
    hit_threshold_pct: float = 1.0,
) -> dict:
    """Simple rule backtest: buy when RSI crosses below threshold, measure forward return."""
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    except Exception as exc:
        return {"symbol": symbol, "ok": False, "error": str(exc)[:80]}

    if hist.empty or len(hist) < 40:
        return {"symbol": symbol, "ok": False, "error": "insufficient history"}

    closes = hist["Close"].dropna()
    rsi = _rsi_series(closes)
    signals: list[float] = []

    for i in range(15, len(closes) - hold_days):
        if rsi.iloc[i] < rsi_buy and rsi.iloc[i - 1] >= rsi_buy:
            entry = float(closes.iloc[i])
            exit_p = float(closes.iloc[i + hold_days])
            if entry > 0:
                signals.append((exit_p / entry - 1) * 100)

    n = len(signals)
    if n == 0:
        return {
            "symbol": symbol,
            "ok": True,
            "signals": 0,
            "hit_rate_pct": None,
            "avg_return_pct": None,
            "rule": f"RSI<{rsi_buy:.0f} then hold {hold_days}d",
        }

    hits = sum(1 for r in signals if r >= hit_threshold_pct)
    avg = sum(signals) / n
    return {
        "symbol": symbol,
        "ok": True,
        "signals": n,
        "hit_rate_pct": round(hits / n * 100, 1),
        "avg_return_pct": round(avg, 2),
        "rule": f"RSI<{rsi_buy:.0f} then hold {hold_days}d",
        "hit_threshold_pct": hit_threshold_pct,
    }


def run_default_rule_backtests(symbols: tuple[str, ...] | None = None) -> list[dict]:
    symbols = symbols or DEFAULT_BACKTEST_SYMBOLS
    return [backtest_rsi_reversal(sym) for sym in symbols]


def signal_validation_report(cfg: dict | None = None) -> dict:
    """Combine resolved pick outcomes with lightweight rule backtests (no ML)."""
    cfg = cfg or load_config()
    stats = get_outcome_stats()
    backtests = run_default_rule_backtests()

    resolved = stats.get("total_resolved") or 0
    confidence = "low"
    if resolved >= 50:
        confidence = "medium"
    if resolved >= 150:
        confidence = "high"

    notes: list[str] = []
    if resolved < 20:
        notes.append(
            f"Only {resolved} resolved desk calls — hit rate is indicative, not statistically stable."
        )
    notes.append(
        "Rule backtests use public Yahoo history (RSI oversold → 7d forward return). "
        "Not predictive — sanity-check for signal design only."
    )
    notes.append("Live feeds: Yahoo Finance + free CoinGecko. Paid/vendor feeds would raise reliability ceiling.")

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "rule_based",
        "confidence": confidence,
        "resolved_outcomes": stats,
        "rule_backtests": backtests,
        "notes": notes,
        "data_sources": ["yfinance", "coingecko", "amfi_nav"],
    }
