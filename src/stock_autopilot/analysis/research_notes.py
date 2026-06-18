from __future__ import annotations

from stock_autopilot.models.schemas import MacroSnapshot, ResearchNote, StockMetrics
from stock_autopilot.universe import brand_cfg


TIER_LABELS = {
    1: "CONSERVATIVE (Capital Preservation)",
    2: "MODERATE (Income + Growth)",
    3: "GROWTH (Aggressive Growth)",
    4: "SPECULATIVE (High Risk / High Reward)",
    5: "TACTICAL (Short-Term Catalyst)",
}


def assign_risk_tier(metrics: StockMetrics, news_sentiment: float, themes: list[str]) -> int:
    defensive = {"Healthcare", "Utilities", "Consumer Defensive", "Consumer Staples"}
    growth = {"Technology", "Communication Services", "Consumer Cyclical"}

    if any(t in themes for t in ("earnings", "m_and_a", "partnership")) and metrics.momentum_3m > 0.08:
        return 5
    if metrics.volatility > 0.40 or (metrics.beta and metrics.beta > 1.5 and metrics.momentum_3m > 0.15):
        return 4
    if metrics.sector in growth and metrics.momentum_3m > 0.05:
        return 3
    if metrics.sector in defensive or (metrics.volatility < 0.20 and metrics.sharpe > 0.5):
        return 1
    return 2


def _rating(score: float, tier: int) -> str:
    if score >= 0.78:
        return "SPECULATIVE BUY" if tier >= 4 else "BUY"
    if score >= 0.62:
        return "BUY" if tier <= 3 else "SPECULATIVE BUY"
    if score >= 0.50:
        return "HOLD"
    return "SELL"


def _conviction(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.60:
        return "MEDIUM"
    return "LOW"


def _trend_label(metrics: StockMetrics) -> str:
    price = metrics.price
    ma50 = metrics.ma_50
    ma200 = metrics.ma_200
    if ma50 and ma200:
        if price > ma50 > ma200:
            return "Bullish"
        if price < ma50 < ma200:
            return "Bearish"
    if metrics.momentum_3m > 0.05:
        return "Bullish"
    if metrics.momentum_3m < -0.05:
        return "Bearish"
    return "Neutral"


def _macd_signal(metrics: StockMetrics) -> str:
    if metrics.macd_hist is None:
        return "Neutral"
    if metrics.macd_hist > 0:
        return "Bullish crossover" if metrics.macd_hist > 0.5 else "Positive momentum"
    return "Bearish crossover" if metrics.macd_hist < -0.5 else "Negative momentum"


def _pattern_label(metrics: StockMetrics) -> str:
    if metrics.momentum_3m > 0.12 and metrics.rsi < 70:
        return "Flag continuation — momentum supported"
    if metrics.rsi > 70:
        return "Extended — watch for mean reversion"
    if metrics.rsi < 35 and metrics.momentum_12m > 0:
        return "Oversold bounce setup"
    return "Base building — range-bound"


def _safe_price(metrics: StockMetrics) -> float:
    price = metrics.price
    if price and price > 0 and price == price:  # exclude NaN
        return price
    if metrics.support and metrics.support > 0:
        return metrics.support
    if metrics.resistance and metrics.resistance > 0:
        return metrics.resistance
    return 1.0


def _price_targets(metrics: StockMetrics, tier: int) -> tuple[float, float, float]:
    from stock_autopilot.investor_profile import get_return_target

    tmin, tmax = get_return_target()
    mid_upside = (tmin + tmax) / 2
    price = _safe_price(metrics)
    tier_bump = {1: 0.0, 2: 0.02, 3: 0.05, 4: 0.10, 5: 0.03}.get(tier, 0.02)
    base_mult = 1 + mid_upside + tier_bump
    bull_mult = base_mult + 0.08
    bear_mult = max(0.65, 1 - mid_upside - 0.04)
    return round(price * bull_mult, 2), round(price * base_mult, 2), round(price * bear_mult, 2)


def _position_sizing(tier: int, conviction: str) -> tuple[str, str, str]:
    base = {1: ("8%", "5%", "0%"), 2: ("6%", "8%", "3%"), 3: ("3%", "6%", "10%"), 4: ("1%", "3%", "5%"), 5: ("0%", "2%", "3%")}.get(
        tier, ("5%", "7%", "4%")
    )
    if conviction == "HIGH" and tier <= 3:
        return base[0], str(min(int(base[1].strip("%")) + 2, 12)) + "%", base[2]
    return base


def _thesis(metrics: StockMetrics, macro: MacroSnapshot, news_sentiment: float, themes: list[str]) -> list[str]:
    points = [
        f"{metrics.sector} exposure with 12M return {metrics.annualized_return * 100:.1f}% and Sharpe {metrics.sharpe:.2f} — "
        f"{'quality risk-adjusted profile' if metrics.sharpe > 0.5 else 'volatile but screening positive'}.",
        f"Macro overlay ({macro.regime}): {'tailwind for risk assets' if 'On' in macro.regime else 'favor quality and sizing discipline' if 'Off' in macro.regime else 'neutral positioning warranted'}.",
    ]
    if news_sentiment > 0.12:
        points.append("Sentiment skew positive on recent headlines — confirm with next earnings print.")
    elif themes:
        points.append(f"Catalyst themes flagged: {', '.join(t.replace('_', ' ') for t in themes[:3])}.")
    else:
        points.append(f"3M momentum {metrics.momentum_3m * 100:+.1f}% with RSI {metrics.rsi:.0f} — technicals {'support continuation' if metrics.momentum_3m > 0 else 'require patience'}.")
    return points[:3]


def build_research_note(
    metrics: StockMetrics,
    macro: MacroSnapshot,
    score: float,
    news_sentiment: float,
    themes: list[str],
    highlights: list[str],
) -> ResearchNote:
    tier = assign_risk_tier(metrics, news_sentiment, themes)
    rating = _rating(score, tier)
    conviction = _conviction(score)
    bull_pt, base_pt, bear_pt = _price_targets(metrics, tier)
    spot = round(_safe_price(metrics), 2)
    upside = round((base_pt / spot - 1) * 100, 1) if spot > 0 else 0.0
    downside = round((1 - bear_pt / spot) * 100, 1) if spot > 0 else 0.0
    trend = _trend_label(metrics)
    cons_pct, bal_pct, agg_pct = _position_sizing(tier, conviction)

    support = metrics.support or round(metrics.price * 0.92, 2)
    resistance = metrics.resistance or round(metrics.price * 1.08, 2)

    risks = []
    if metrics.volatility > 0.30:
        risks.append(("Elevated volatility", "HIGH"))
    elif metrics.volatility > 0.22:
        risks.append(("Above-average price swings", "MED"))
    else:
        risks.append(("Macro regime shift could compress multiples", "MED"))
    if news_sentiment < -0.1:
        risks.append(("Negative headline flow", "HIGH"))
    else:
        risks.append(("Earnings revision risk", "MED"))
    if metrics.region not in ("north_america", "North America", "global_etfs", "Global"):
        risks.append(("FX / geopolitical exposure", "MED"))
    else:
        risks.append(("Sector concentration vs. broad market", "LOW"))

    near_cat = highlights[0] if highlights else f"Monitor next earnings and {metrics.sector} sector rotation."
    med_cat = f"Macro path under {macro.regime} — watch rates and {metrics.sector} relative strength."
    long_cat = f"Structural {metrics.sector} thesis contingent on margin and revenue durability."

    thesis_breaker = f"Sustained break below ${support:.2f} on volume invalidates base-case setup."

    desk = (
        f"The desk likes {metrics.symbol} for asymmetric risk/reward at Tier {tier} — "
        f"the market may be underpricing {metrics.sector} quality amid {macro.regime.lower()} conditions."
        if score >= 0.65
        else f"{metrics.symbol} screens mixed — size conservatively until catalyst clarity improves."
    )

    return ResearchNote(
        risk_tier=tier,
        risk_tier_label=TIER_LABELS[tier],
        rating=rating,
        conviction=conviction,
        price_target=base_pt,
        current_price=spot,
        upside_pct=upside,
        downside_pct=downside,
        industry=metrics.industry or metrics.sector,
        thesis=_thesis(metrics, macro, news_sentiment, themes),
        revenue_growth_yoy=metrics.revenue_growth_yoy,
        gross_margin=metrics.gross_margin,
        operating_margin=metrics.operating_margin,
        pe_forward=metrics.pe_forward,
        ev_ebitda=metrics.ev_ebitda,
        peg_ratio=metrics.peg_ratio,
        fcf_yield=metrics.fcf_yield,
        debt_to_equity=metrics.debt_to_equity,
        roe=metrics.roe,
        roic=metrics.roic,
        trend=trend,
        rsi=metrics.rsi,
        macd_signal=_macd_signal(metrics),
        support=support,
        resistance=resistance,
        pattern=_pattern_label(metrics),
        catalyst_near=near_cat[:120],
        catalyst_medium=med_cat[:120],
        catalyst_long=long_cat[:120],
        risks=risks[:3],
        bull_case_price=bull_pt,
        bull_case_prob=25 if tier >= 4 else 30,
        bull_case_note="Multiple expansion + estimate revisions",
        base_case_price=base_pt,
        base_case_prob=50,
        base_case_note="Earnings track consensus; macro stable",
        bear_case_price=bear_pt,
        bear_case_prob=25 if tier >= 4 else 20,
        bear_case_note="Multiple compression or growth deceleration",
        size_conservative=cons_pct,
        size_balanced=bal_pct,
        size_aggressive=agg_pct,
        take_profit=f"${base_pt:.2f} (base target) or Tier downgrade",
        stop_loss=f"${support:.2f} (support break)",
        thesis_breaker=thesis_breaker,
        desk_comment=desk,
    )


def format_research_note_text(note: ResearchNote, symbol: str, name: str, sector: str) -> str:
    def pct(v: float | None, suffix: str = "%") -> str:
        if v is None:
            return "N/A"
        if suffix == "%" and abs(v) < 5:
            return f"{v * 100:.1f}%"
        return f"{v:.2f}{suffix}" if suffix != "%" else f"{v:.1f}%"

    fund_lines = [
        f"- Revenue Growth (YoY): {pct(note.revenue_growth_yoy)}",
        f"- Gross Margin: {pct(note.gross_margin)} | Operating Margin: {pct(note.operating_margin)}",
        f"- P/E (fwd): {pct(note.pe_forward, '')} | EV/EBITDA: {pct(note.ev_ebitda, 'x')} | PEG: {pct(note.peg_ratio, '')}",
        f"- FCF Yield: {pct(note.fcf_yield)} | Debt/Equity: {pct(note.debt_to_equity, '')}",
        f"- ROE: {pct(note.roe)} | ROIC: {pct(note.roic)}",
    ]

    thesis = "\n".join(f"- {t}" for t in note.thesis)
    risks = "\n".join(f"- {r[0]} — Severity: {r[1]}" for r in note.risks)

    return f"""═══════════════════════════════════════════════
{brand_cfg()['research_header']}
═══════════════════════════════════════════════
TICKER: {symbol} | {name}
SECTOR: {sector} | INDUSTRY: {note.industry}
RISK TIER: {note.risk_tier} — {note.risk_tier_label}
RATING: {note.rating} | CONVICTION: {note.conviction}
PRICE TARGET: ${note.price_target:.2f} (12-month) | CURRENT: ${note.current_price:.2f}
UPSIDE/DOWNSIDE: +{note.upside_pct:.1f}% / -{note.downside_pct:.1f}%

━━━ INVESTMENT THESIS ━━━
{thesis}

━━━ FUNDAMENTAL SNAPSHOT ━━━
{chr(10).join(fund_lines)}

━━━ TECHNICAL SETUP ━━━
- Trend: {note.trend}
- RSI: {note.rsi:.0f} | MACD: {note.macd_signal}
- Key Support: ${note.support:.2f} | Key Resistance: ${note.resistance:.2f}
- Pattern: {note.pattern}

━━━ CATALYSTS ━━━
- Near-term (0–3 months): {note.catalyst_near}
- Medium-term (3–12 months): {note.catalyst_medium}
- Long-term (1–3 years): {note.catalyst_long}

━━━ RISK FACTORS ━━━
{risks}

━━━ SCENARIO ANALYSIS ━━━
- Bull Case (${note.bull_case_price:.2f} — {note.bull_case_prob}% prob): {note.bull_case_note}
- Base Case (${note.base_case_price:.2f} — {note.base_case_prob}% prob): {note.base_case_note}
- Bear Case (${note.bear_case_price:.2f} — {note.bear_case_prob}% prob): {note.bear_case_note}

━━━ POSITION SIZING GUIDANCE ━━━
- Conservative Portfolio: {note.size_conservative}
- Balanced Portfolio: {note.size_balanced}
- Aggressive Portfolio: {note.size_aggressive}

━━━ EXIT CRITERIA ━━━
- Take Profit: {note.take_profit}
- Stop Loss: {note.stop_loss}
- Thesis Breaker: {note.thesis_breaker}

DESK COMMENT: {note.desk_comment}
═══════════════════════════════════════════════"""


def format_macro_briefing(macro: MacroSnapshot) -> str:
    """Institutional-style macro desk briefing."""
    ind = macro.indicators or {}
    lines = [
        f"Desk assessment: {macro.regime} environment (risk score {macro.risk_score:.2f}).",
        macro.summary,
    ]
    for key, label in (("vix", "VIX"), ("sp500_1m_pct", "S&P 500 1M %"), ("us_10y_yield", "US 10Y yield")):
        val = ind.get(key)
        if val is not None:
            lines.append(f"{label}: {val}.")
    lines.append("Sector rotation: favor quality compounders in Risk-Off; growth/momentum in Risk-On.")
    return " ".join(lines)
