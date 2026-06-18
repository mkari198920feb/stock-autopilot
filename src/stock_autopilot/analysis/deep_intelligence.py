from __future__ import annotations

from datetime import datetime, timezone

from stock_autopilot.analysis.research_notes import TIER_LABELS, assign_risk_tier, build_research_note
from stock_autopilot.collectors.deep_data import fetch_deep_bundle
from stock_autopilot.collectors.market import fetch_stock_metrics
from stock_autopilot.collectors.news import aggregate_news_sentiment, fetch_news_for_symbol
from stock_autopilot.collectors.macro import analyze_global_conditions
from stock_autopilot.investor_profile import get_return_target
from stock_autopilot.models.schemas import DeepStockBrief, MacroSnapshot, StockMetrics
from stock_autopilot.universe import all_tickers, brand_cfg, load_config, ticker_region_map


def _fmt_money(val: float | None, currency: str = "USD") -> str:
    if val is None:
        return "—"
    sym = "₹" if currency == "INR" else "$"
    if abs(val) >= 1e12:
        return f"{sym}{val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"{sym}{val/1e9:.2f}B"
    if abs(val) >= 1e7:
        return f"{sym}{val/1e7:.2f}Cr"
    if abs(val) >= 1e6:
        return f"{sym}{val/1e6:.2f}M"
    return f"{sym}{val:,.2f}"


def _cap_segment(mcap: float | None, currency: str) -> str:
    if not mcap:
        return "—"
    if currency == "INR":
        if mcap >= 1e12:
            return "Large Cap"
        if mcap >= 5e10:
            return "Mid Cap"
        return "Small Cap"
    if mcap >= 200e9:
        return "Large Cap"
    if mcap >= 10e9:
        return "Mid Cap"
    return "Small Cap"


def _moat_note(industry: str, roe: float | None, gross_margin: float | None) -> str:
    if gross_margin and gross_margin > 0.5:
        return "Intangible asset / brand — high gross margins suggest pricing power"
    if "Software" in industry or "Semiconductor" in industry:
        return "Switching cost — embedded workflows and ecosystem lock-in"
    if roe and roe > 18:
        return "Cost advantage / efficient scale — sustained high returns on capital"
    return "Efficient scale — competitive position supported by sector economics"


def _verdict(rating: str, upside: float, rsi: float, change_pct: float) -> str:
    if "SELL" in rating.upper():
        return "AVOID"
    if upside < 5 and rsi > 72:
        return "WATCHLIST"
    if upside < 0:
        return "RESEARCH MORE"
    if "BUY" in rating.upper() and upside >= 8:
        return "BUY"
    return "WATCHLIST"


def _build_peers(symbol: str, sector: str, bundle: dict) -> dict:
    cfg = load_config()
    region_map = ticker_region_map(cfg)
    peers = [s for s in all_tickers(cfg) if s != symbol][:40]
    peer_rows = []
    for ps in peers:
        m = fetch_stock_metrics(ps, region_map.get(ps, "Global"), 180)
        if m and m.sector == sector:
            peer_rows.append(m)
        if len(peer_rows) >= 3:
            break

    def _row(m: StockMetrics) -> dict:
        return {
            "symbol": m.symbol,
            "revenue_growth": round((m.revenue_growth_yoy or 0) * 100, 1),
            "margin": round((m.operating_margin or m.gross_margin or 0) * 100, 1) if m.operating_margin or m.gross_margin else None,
            "roe": round((m.roe or 0) * 100, 1) if m.roe and m.roe < 2 else m.roe,
            "pe_forward": m.pe_forward,
            "ev_ebitda": m.ev_ebitda,
            "debt_equity": m.debt_to_equity,
        }

    subject = {
        "symbol": symbol,
        "revenue_growth": round((bundle.get("revenue_growth_yoy") or 0) * 100, 1),
        "margin": round((bundle.get("operating_margin") or bundle.get("gross_margin") or 0) * 100, 1),
        "roe": bundle.get("roe"),
        "pe_forward": bundle.get("pe_forward"),
        "ev_ebitda": bundle.get("ev_ebitda"),
        "debt_equity": bundle.get("debt_equity"),
    }
    peer_table = [_row(m) for m in peer_rows]
    sector_pe = bundle.get("pe_forward") or bundle.get("pe_trailing")
    verdict = "In line with peer set on headline multiples."
    if peer_rows and sector_pe:
        avg_pe = sum(m.pe_forward or m.pe_ratio or 0 for m in peer_rows if (m.pe_forward or m.pe_ratio)) / max(
            len([m for m in peer_rows if (m.pe_forward or m.pe_ratio)]), 1
        )
        if avg_pe and sector_pe < avg_pe * 0.85:
            verdict = f"Trades at ~{round((1 - sector_pe/avg_pe)*100)}% discount to closest peers despite comparable quality metrics."
        elif avg_pe and sector_pe > avg_pe * 1.15:
            verdict = f"Premium of ~{round((sector_pe/avg_pe - 1)*100)}% vs peers — needs catalyst to justify."

    return {"subject": subject, "peers": peer_table, "verdict": verdict}


def build_deep_brief(symbol: str, trigger_context: str = "") -> DeepStockBrief | None:
    from stock_autopilot.collectors.symbol_normalize import to_yahoo_symbol

    sym = to_yahoo_symbol(symbol)
    bundle = fetch_deep_bundle(sym)
    if not bundle:
        return None

    cfg = load_config()
    region_map = ticker_region_map(cfg)
    metrics = fetch_stock_metrics(sym, region_map.get(sym, "Global"))
    macro = analyze_global_conditions(cfg.get("macro_symbols", {}))
    news = fetch_news_for_symbol(sym, limit=8)
    sent, _, themes = aggregate_news_sentiment(news)

    score = 0.62
    tier = 3
    note = None
    if metrics:
        from stock_autopilot.analysis.scorer import score_stock

        weights = cfg.get("scoring", {}).get("weights", {})
        score = score_stock(metrics, macro, sent, weights)
        tier = assign_risk_tier(metrics, sent, themes)
        note = build_research_note(metrics, macro, score, sent, themes, [])

    tmin, tmax = get_return_target()
    target = note.price_target if note else bundle["cmp"] * (1 + (tmin + tmax) / 2)
    upside = (target / bundle["cmp"] - 1) * 100 if bundle["cmp"] else 0
    rating = note.rating if note else ("BUY" if score >= 0.62 else "HOLD")
    conviction = note.conviction if note else ("HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.6 else "LOW")
    horizon = "Medium term" if tier <= 3 else "Short term" if tier >= 5 else "Long term"

    currency = bundle["currency"]
    roe = bundle.get("roe")
    gross = bundle.get("gross_margin")
    if gross and gross < 2:
        gross *= 100

    business = bundle.get("summary") or (
        f"{bundle['name']} operates in {bundle['industry']} within {bundle['sector']}. "
        f"Revenue model driven by core operations with {bundle.get('employees') or 'global'} workforce scale."
    )
    business_short = business[:420] + ("…" if len(business) > 420 else "")

    pillar_business = {
        "business_model": business_short,
        "revenue_streams": f"Primary: {bundle['industry']}. Revenue growth YoY: {round((bundle.get('revenue_growth_yoy') or 0)*100, 1)}%.",
        "moat_type": _moat_note(bundle["industry"], roe, gross),
        "industry_position": f"Sector: {bundle['sector']} — {bundle['industry']}",
        "management": "Review insider activity via exchange filings; institutional ownership "
        f"{round((bundle.get('held_percent_institutions') or 0)*100, 1)}%.",
    }

    pillar_financials = {
        "revenue_quarters": bundle.get("revenue_quarters") or [],
        "revenue_growth_yoy_pct": round((bundle.get("revenue_growth_yoy") or 0) * 100, 1),
        "gross_margin_pct": round(gross, 1) if gross else None,
        "operating_margin_pct": round((bundle.get("operating_margin") or 0) * 100, 1) if bundle.get("operating_margin") else None,
        "net_margin_pct": round((bundle.get("profit_margin") or 0) * 100, 1) if bundle.get("profit_margin") else None,
        "eps_ttm": bundle.get("eps_ttm"),
        "roe_pct": round(roe, 1) if roe else None,
        "roce_proxy_pct": round(bundle.get("roa"), 1) if bundle.get("roa") else None,
        "debt_equity": bundle.get("debt_equity"),
        "current_ratio": bundle.get("current_ratio"),
        "fcf": bundle.get("fcf"),
        "fcf_yield_pct": round(bundle.get("fcf_yield"), 2) if bundle.get("fcf_yield") else None,
        "net_debt": bundle.get("net_debt"),
    }

    pe = bundle.get("pe_trailing")
    pe_fwd = bundle.get("pe_forward")
    dcf_fair = bundle["cmp"] * (1 + (tmin + tmax) / 2) if note is None else target
    margin_of_safety = (dcf_fair / bundle["cmp"] - 1) * 100 if bundle["cmp"] else 0

    pillar_valuation = {
        "pe_trailing": round(pe, 1) if pe else None,
        "pe_forward": round(pe_fwd, 1) if pe_fwd else None,
        "pb": round(bundle.get("pb"), 2) if bundle.get("pb") else None,
        "ev_ebitda": round(bundle.get("ev_ebitda"), 1) if bundle.get("ev_ebitda") else None,
        "peg": round(bundle.get("peg"), 2) if bundle.get("peg") else None,
        "fcf_yield_pct": round(bundle.get("fcf_yield"), 2) if bundle.get("fcf_yield") else None,
        "dcf_fair_value": round(dcf_fair, 2),
        "margin_of_safety_pct": round(margin_of_safety, 1),
        "verdict": "Discount to desk target band" if margin_of_safety > 5 else "Fair to premium vs desk model",
    }

    ma50 = bundle.get("ma50")
    ma200 = bundle.get("ma200")
    cmp = bundle["cmp"]
    pillar_technical = {
        "vs_ma20_pct": round((cmp / bundle["ma20"] - 1) * 100, 1) if bundle.get("ma20") else None,
        "vs_ma50_pct": round((cmp / ma50 - 1) * 100, 1) if ma50 else None,
        "vs_ma200_pct": round((cmp / ma200 - 1) * 100, 1) if ma200 else None,
        "ma200_slope": bundle.get("ma200_slope") or "—",
        "primary_trend": note.trend if note else ("Bullish" if bundle.get("momentum_3m", 0) > 0.05 else "Bearish" if bundle.get("momentum_3m", 0) < -0.05 else "Sideways"),
        "rsi": round(bundle.get("rsi") or 50, 1),
        "macd": note.macd_signal if note else ("Bullish" if (bundle.get("macd_hist") or 0) > 0 else "Bearish"),
        "volume_vs_avg_pct": round(bundle.get("volume_vs_avg_pct") or 100, 1),
        "week_52_high": round(bundle["week_52_high"], 2),
        "week_52_low": round(bundle["week_52_low"], 2),
        "support": round(bundle.get("support") or 0, 2),
        "resistance": round(bundle.get("resistance") or 0, 2),
        "pattern": note.pattern if note else "—",
    }

    pillar_ownership = {
        "insider_pct": round((bundle.get("held_percent_insiders") or 0) * 100, 1),
        "institutional_pct": round((bundle.get("held_percent_institutions") or 0) * 100, 1),
        "insight": "Institutional ownership elevated — validate with latest exchange shareholding pattern.",
        "bulk_deals_note": "Bulk/block deal feed requires exchange terminal — check NSE/BSE announcements for India names.",
    }

    catalysts = []
    if note:
        if note.catalyst_near:
            catalysts.append({"horizon": "0–90 days", "event": note.catalyst_near, "probability": "MEDIUM"})
        if note.catalyst_medium:
            catalysts.append({"horizon": "3–12 months", "event": note.catalyst_medium, "probability": "MEDIUM"})
        if note.catalyst_long:
            catalysts.append({"horizon": "1–3 years", "event": note.catalyst_long, "probability": "LOW"})
    if not catalysts:
        catalysts = [
            {"horizon": "0–90 days", "event": "Next earnings / macro data print", "probability": "MEDIUM"},
            {"horizon": "3–12 months", "event": f"{macro.regime} regime path", "probability": "MEDIUM"},
        ]

    risks = []
    if note and note.risks:
        for r, sev in note.risks[:3]:
            risks.append({"risk": r, "severity": sev, "mitigant": "Size to tier; respect stop level."})
    else:
        risks = [
            {"risk": "Macro / rate shock", "severity": "MED", "mitigant": "Diversify; reduce size in Risk-Off."},
            {"risk": "Multiple compression if growth slows", "severity": "MED", "mitigant": "Track quarterly revenue trend."},
        ]

    peers = _build_peers(sym, bundle["sector"], bundle)
    analyst = bundle.get("analyst") or {}
    tgt_mean = analyst.get("target_mean")
    analyst_block = {
        "num_analysts": analyst.get("num_analysts") or 0,
        "target_mean": tgt_mean,
        "target_high": analyst.get("target_high"),
        "target_low": analyst.get("target_low"),
        "street_upside_pct": round((tgt_mean / cmp - 1) * 100, 1) if tgt_mean and cmp else None,
        "recommendation_key": bundle.get("recommendation_key") or "—",
    }

    stop = round(bundle.get("support") or cmp * 0.92, 2)
    position = {
        "entry_zone": f"{round(cmp * 0.98, 2)} – {round(cmp * 1.02, 2)}",
        "add_more": round(bundle.get("support") or cmp * 0.95, 2),
        "target_6m": round(cmp * 1.06, 2),
        "target_12m": round(target, 2),
        "stop_loss": stop,
        "thesis_breaker": note.thesis_breaker if note else "Close below major support on volume with deteriorating fundamentals.",
    }

    reasons = []
    if roe and roe > 15:
        reasons.append(f"ROE {roe:.0f}% clears quality threshold (>15%) — capital compounding profile.")
    if upside > 8:
        reasons.append(f"Desk target implies +{upside:.0f}% upside vs CMP — aligns with your return band.")
    if bundle.get("volume_vs_avg_pct", 0) > 120 and bundle.get("change_pct", 0) > 0:
        reasons.append(f"Volume {bundle['volume_vs_avg_pct']:.0f}% of 20D avg on green day — accumulation signal.")
    if not reasons and note and note.thesis:
        reasons = note.thesis[:3]
    while len(reasons) < 3:
        reasons.append(f"Macro regime {macro.regime} supports {bundle['sector']} positioning at current score {int(score*100)}.")

    why = (
        f"We {'recommend' if 'BUY' in rating else 'flag'} {bundle['name']} because "
        f"quality metrics (ROE {roe or '—'}%, margin profile) and technical structure "
        f"({pillar_technical['primary_trend']}, RSI {pillar_technical['rsi']}) align with a "
        f"{rating} view and {round(upside)}% desk upside. {peers['verdict']}"
    )

    risk_lines = [f"{r['risk']} ({r['severity']})" for r in risks[:2]]
    desk_verdict = (
        f"Market may be under-appreciating {bundle['sector']} cash-flow durability at {pe or '—'}x trailing P/E. "
        f"Desk view: {conviction} conviction {rating} for {horizon.lower()} holders."
    )

    verdict = _verdict(rating, upside, pillar_technical["rsi"], bundle["change_pct"])
    if trigger_context == "52w_high" and pillar_technical["rsi"] > 68:
        verdict = "WATCHLIST"
        desk_verdict += " At 52W high with elevated RSI — chase only on pullback to support."
    elif trigger_context == "52w_low":
        verdict = "RESEARCH MORE" if upside < 10 else "BUY"
        desk_verdict += " At 52W low — verify whether this is value or a falling knife via next earnings."

    financials_glance = {
        "revenue_growth_yoy": pillar_financials["revenue_growth_yoy_pct"],
        "ebitda_margin": pillar_financials["operating_margin_pct"],
        "net_margin": pillar_financials["net_margin_pct"],
        "eps": bundle.get("eps_ttm"),
        "fcf": _fmt_money(bundle.get("fcf"), currency),
        "roe": pillar_financials["roe_pct"],
        "debt_equity": bundle.get("debt_equity"),
    }

    brief = DeepStockBrief(
        symbol=sym,
        name=bundle["name"],
        exchange=str(bundle["exchange"]),
        sector=bundle["sector"],
        industry=bundle["industry"],
        currency=currency,
        cmp=round(cmp, 2),
        change_pct=round(bundle["change_pct"], 2),
        change_abs=round(bundle["change_abs"], 2),
        week_52_high=round(bundle["week_52_high"], 2),
        week_52_low=round(bundle["week_52_low"], 2),
        week_52_high_dist_pct=round(bundle["week_52_high_dist_pct"], 1),
        week_52_low_dist_pct=round(bundle["week_52_low_dist_pct"], 1),
        market_cap=bundle.get("market_cap"),
        cap_segment=_cap_segment(bundle.get("market_cap"), currency),
        rating=rating,
        target_price=round(target, 2),
        upside_pct=round(upside, 1),
        risk_tier=tier,
        conviction=conviction,
        horizon=horizon,
        verdict=verdict,
        why_recommending=why,
        top_reasons=reasons[:3],
        top_risks=risk_lines,
        business_snapshot=business_short,
        pillars={
            "business_quality": pillar_business,
            "financial_evidence": pillar_financials,
            "valuation_evidence": pillar_valuation,
            "technical_evidence": pillar_technical,
            "ownership_evidence": pillar_ownership,
            "growth_evidence": {"catalysts": catalysts, "analyst": analyst_block},
            "risk_evidence": {"risks": risks},
            "peer_comparison": peers,
        },
        financials_glance=financials_glance,
        valuation=pillar_valuation,
        technical=pillar_technical,
        ownership=pillar_ownership,
        catalysts=catalysts,
        peer_comparison=peers,
        position_guide=position,
        analyst_consensus=analyst_block,
        desk_verdict=desk_verdict,
        card_text=_format_card(
            bundle, rating, target, upside, tier, conviction, horizon, verdict, why, reasons, risk_lines, desk_verdict
        ),
        generated_at=datetime.now(timezone.utc),
        trigger_context=trigger_context,
    )
    return brief


def _format_card(
    b, rating, target, upside, tier, conviction, horizon, verdict, why, reasons, risks, desk
) -> str:
    c = b["currency"]
    sym = "₹" if c == "INR" else "$"
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  {brand_cfg()['brand_name'].upper()} DEEP INTELLIGENCE — FULL STOCK BRIEF",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  {b['name']}  |  {b['exchange']}:{b['symbol']}  |  {b['sector']}",
        f"║  CMP: {sym}{b['cmp']:,.2f}  |  Today: {b['change_pct']:+.2f}%",
        f"║  52W High: {sym}{b['week_52_high']:,.2f} ({b['week_52_high_dist_pct']:.0f}% away)",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  RATING: {rating}  |  TARGET: {sym}{target:,.2f}  |  UPSIDE: +{upside:.0f}%",
        f"║  RISK TIER: {tier} ({TIER_LABELS.get(tier, '')})  |  {conviction}  |  {horizon}",
        f"║  VERDICT: {verdict}",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  ★ WHY WE ARE RECOMMENDING THIS STOCK ★",
        f"║  {why[:120]}",
    ]
    for i, r in enumerate(reasons[:3], 1):
        lines.append(f"║  {i}. {r[:70]}")
    for r in risks[:2]:
        lines.append(f"║  ⚠ {r[:65]}")
    lines.extend(
        [
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  DESK VERDICT: {desk[:100]}",
            "╚══════════════════════════════════════════════════════════════╝",
        ]
    )
    return "\n".join(lines)
