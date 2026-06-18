from __future__ import annotations

from stock_autopilot.analysis.scorer import score_stock
from stock_autopilot.collectors.india_market import cap_segment, nse_symbol
from stock_autopilot.models.schemas import IndiaEquityPick, IndiaMacroBar, StockMetrics
from stock_autopilot.universe import brand_cfg

TIER_LABELS = {
    1: "CONSERVATIVE — Nifty Blue Chips",
    2: "MODERATE — Quality Mid / Next 50",
    3: "GROWTH — Emerging Mid & Small",
    4: "SPECULATIVE — Small / Turnaround",
    5: "TACTICAL — Event / Momentum",
}

TAX_NOTE = (
    "STCG @ 20% if held < 1 year; LTCG @ 12.5% above ₹1.25L exemption if held > 1 year. "
    "Dividend taxable per slab (TDS @ 10% if > ₹5,000)."
)


def _india_macro_score(metrics: StockMetrics, macro: IndiaMacroBar) -> float:
    s = 0.65
    if macro.brent_impact.startswith("Bearish") and metrics.sector in ("Energy", "Utilities"):
        s += 0.15
    if macro.brent_impact.startswith("Bullish") and metrics.sector in ("Consumer Defensive", "Fast Moving Consumer Goods"):
        s += 0.1
    if macro.inr_change_pct and macro.inr_change_pct > 0.5 and metrics.sector in ("Technology", "Information Technology"):
        s -= 0.15
    if macro.inr_change_pct and macro.inr_change_pct < -0.3 and metrics.sector in ("Technology", "Information Technology"):
        s += 0.15
    if macro.vix_sentiment == "Fear" and metrics.volatility < 0.25:
        s += 0.1
    if macro.pe_assessment == "Expensive" and metrics.pe_ratio and metrics.pe_ratio > 35:
        s -= 0.15
    return max(0.2, min(1.0, s))


def assign_india_tier(metrics: StockMetrics, score: float) -> int:
    seg = cap_segment(metrics.symbol, None)
    if seg == "Large Cap" and metrics.volatility < 0.28 and score >= 0.65:
        return 1
    if seg == "Large Cap" or (seg == "Mid Cap" and score >= 0.6):
        return 2
    if metrics.volatility > 0.38 or score < 0.55:
        return 4 if metrics.volatility > 0.45 else 3
    if metrics.momentum_3m > 0.15 and metrics.rsi > 70:
        return 5
    return 3


def _rating(score: float, tier: int) -> str:
    if score >= 0.72:
        return "ACCUMULATE" if tier <= 2 else "BUY"
    if score >= 0.58:
        return "BUY" if tier <= 3 else "ACCUMULATE"
    if score >= 0.48:
        return "HOLD"
    return "REDUCE"


def _conviction(score: float) -> str:
    if score >= 0.72:
        return "HIGH"
    if score >= 0.58:
        return "MEDIUM"
    return "LOW"


def _risk_class(tier: int) -> str:
    return {1: "green", 2: "green", 3: "yellow", 4: "red", 5: "red"}.get(tier, "yellow")


def _format_note(pick: IndiaEquityPick) -> str:
    fin = pick.financials
    tech = pick.technicals
    risks = "\n".join(f"- {r[0]} — {r[1]}" for r in pick.risks)
    thesis = "\n".join(f"- {t}" for t in pick.thesis)
    return f"""═══════════════════════════════════════════════════════
{brand_cfg()['india_header']}
═══════════════════════════════════════════════════════
STOCK      : {pick.name} | NSE: {pick.nse} | BSE: {pick.bse}
SECTOR     : {pick.sector} | INDUSTRY: {pick.industry}
MARKET CAP : {pick.cap_segment}
RISK TIER  : {pick.risk_tier} — {pick.risk_tier_label}
RATING     : {pick.rating} | CONVICTION: {pick.conviction}
CMP        : ₹{pick.cmp:,.2f} | TARGET (12M): ₹{pick.target_12m:,.2f} | UPSIDE: +{pick.upside_pct:.1f}%

━━━ INVESTMENT THESIS ━━━
{thesis}

━━━ FINANCIAL SNAPSHOT ━━━
- Revenue Growth (YoY)  : {fin.get('revenue_growth', 'N/A')}
- P/E (fwd)             : {fin.get('pe_forward', 'N/A')}
- ROE                   : {fin.get('roe', 'N/A')} | Debt/Equity: {fin.get('debt_equity', 'N/A')}

━━━ TECHNICAL SETUP ━━━
- Trend         : {tech.get('trend', 'Neutral')}
- 50-DMA / 200-DMA : ₹{tech.get('ma50', '—')} / ₹{tech.get('ma200', '—')}
- RSI (14)      : {tech.get('rsi', '—')} | Support: ₹{tech.get('support', '—')} | Resistance: ₹{tech.get('resistance', '—')}

━━━ RISKS ━━━
{risks}

━━━ TAX IMPLICATIONS ━━━
{pick.tax_note}

━━━ POSITION SIZING ━━━
- Conservative: {pick.position_sizing.get('conservative', '—')}
- Balanced: {pick.position_sizing.get('balanced', '—')}
- Aggressive: {pick.position_sizing.get('aggressive', '—')}

━━━ DESK NOTE ━━━
{pick.desk_note}

Consult your SEBI-registered financial advisor before investing.
═══════════════════════════════════════════════════════"""


def build_india_equity_pick(
    metrics: StockMetrics,
    macro: IndiaMacroBar,
    score: float,
    bse_map: dict[str, str],
) -> IndiaEquityPick:
    tier = assign_india_tier(metrics, score)
    rating = _rating(score, tier)
    conviction = _conviction(score)
    target = round(metrics.price * (1.08 + (score - 0.5) * 0.2), 2)
    upside = round((target / metrics.price - 1) * 100, 1) if metrics.price else 0

    trend = "Bullish" if metrics.price > (metrics.ma_50 or metrics.price) else "Bearish"
    if metrics.ma_50 and metrics.ma_200:
        if metrics.price > metrics.ma_50 > metrics.ma_200:
            trend = "Bullish"
        elif metrics.price < metrics.ma_50 < metrics.ma_200:
            trend = "Bearish"
        else:
            trend = "Sideways"

    thesis = [
        f"{metrics.sector} name with 12M return {metrics.annualized_return * 100:.1f}% — "
        f"{'quality compounder' if metrics.sharpe > 0.4 else 'volatile but screening positive'} profile.",
        f"India macro: Nifty {macro.pe_assessment.lower()} (PE {macro.nifty_pe or '—'}), "
        f"RBI {macro.rbi_stance.lower()}, {macro.brent_impact.split('(')[0].strip()}.",
        f"3M momentum {metrics.momentum_3m * 100:+.1f}%, RSI {metrics.rsi:.0f} — "
        f"{'institutional accumulation zone' if metrics.momentum_3m > 0 and metrics.rsi < 65 else 'wait for better entry' if metrics.rsi > 68 else 'neutral setup'}.",
    ]

    risks: list[tuple[str, str]] = [
        ("FII flow reversal / global risk-off", "MED"),
        ("INR depreciation / crude spike", "MED" if macro.brent_impact.startswith("Bearish") else "LOW"),
        ("Sector-specific earnings miss", "MED"),
    ]
    if metrics.volatility > 0.35:
        risks.insert(0, ("High beta / circuit risk", "HIGH"))

    sizing = {
        1: ("8%", "6%", "0%"),
        2: ("6%", "8%", "4%"),
        3: ("3%", "6%", "8%"),
        4: ("1%", "2%", "3%"),
        5: ("0%", "2%", "3%"),
    }.get(tier, ("4%", "6%", "4%"))

    nse = nse_symbol(metrics.symbol)
    pick = IndiaEquityPick(
        symbol=metrics.symbol,
        nse=nse,
        bse=bse_map.get(metrics.symbol, nse),
        name=metrics.name,
        sector=metrics.sector,
        industry=metrics.industry or metrics.sector,
        cap_segment=cap_segment(metrics.symbol, None),
        score=round(score, 4),
        risk_tier=tier,
        risk_tier_label=TIER_LABELS[tier],
        rating=rating,
        conviction=conviction,
        cmp=round(metrics.price, 2),
        target_12m=target,
        upside_pct=upside,
        thesis=thesis,
        financials={
            "revenue_growth": f"{metrics.revenue_growth_yoy * 100:.1f}%" if metrics.revenue_growth_yoy else "N/A",
            "pe_forward": f"{metrics.pe_forward:.1f}x" if metrics.pe_forward else "N/A",
            "roe": f"{metrics.roe * 100:.1f}%" if metrics.roe else "N/A",
            "debt_equity": f"{metrics.debt_to_equity:.2f}" if metrics.debt_to_equity else "N/A",
        },
        technicals={
            "trend": trend,
            "ma50": f"{metrics.ma_50:,.0f}" if metrics.ma_50 else "—",
            "ma200": f"{metrics.ma_200:,.0f}" if metrics.ma_200 else "—",
            "rsi": f"{metrics.rsi:.0f}",
            "support": f"{metrics.support:,.0f}" if metrics.support else "—",
            "resistance": f"{metrics.resistance:,.0f}" if metrics.resistance else "—",
        },
        catalysts={
            "near": "Upcoming quarterly results / sector policy",
            "medium": "Capacity / order book visibility",
            "long": "India consumption & capex cycle",
        },
        risks=risks,
        tax_note=TAX_NOTE,
        position_sizing={
            "conservative": sizing[0],
            "balanced": sizing[1],
            "aggressive": sizing[2],
        },
        exit_criteria={
            "target": f"₹{target:,.0f}",
            "stop": f"₹{metrics.support:,.0f}" if metrics.support else f"₹{metrics.price * 0.92:,.0f}",
            "breaker": "Sustained break below 200-DMA on volume",
        },
        desk_note=(
            f"Street is {'underappreciating' if score >= 0.65 else 'fairly pricing'} "
            f"{nse}'s {metrics.sector.lower()} positioning amid {macro.rbi_stance.lower()} RBI cycle."
        ),
        risk_class=_risk_class(tier),
    )
    pick.research_note_text = _format_note(pick)
    return pick


def rank_india_equities(
    metrics_list: list[StockMetrics],
    macro: IndiaMacroBar,
    weights: dict[str, float],
    bse_map: dict[str, str],
    daily_picks: int = 6,
    max_per_sector: int = 2,
) -> list[IndiaEquityPick]:
    base_weights = weights or {
        "momentum": 0.25,
        "valuation": 0.15,
        "volatility_fit": 0.15,
        "news_sentiment": 0.15,
        "macro_alignment": 0.30,
    }

    from stock_autopilot.models.schemas import MacroSnapshot
    from datetime import datetime, timezone

    pseudo_macro = MacroSnapshot(
        captured_at=datetime.now(timezone.utc),
        regime="India / " + macro.rbi_stance,
        risk_score=0.5 if macro.vix_sentiment == "Neutral" else 0.7,
        summary=macro.ticker_text,
    )

    scored: list[tuple[float, StockMetrics]] = []
    for m in metrics_list:
        s = score_stock(m, pseudo_macro, 0.0, base_weights)
        s = s * 0.7 + _india_macro_score(m, macro) * 0.3
        scored.append((s, m))
    scored.sort(key=lambda x: x[0], reverse=True)

    picks: list[IndiaEquityPick] = []
    sector_count: dict[str, int] = {}
    for score, m in scored:
        if len(picks) >= daily_picks:
            break
        if sector_count.get(m.sector, 0) >= max_per_sector:
            continue
        sector_count[m.sector] = sector_count.get(m.sector, 0) + 1
        picks.append(build_india_equity_pick(m, macro, score, bse_map))
    return picks
