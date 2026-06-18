from __future__ import annotations

from stock_autopilot.analysis.research_notes import build_research_note, format_research_note_text
from stock_autopilot.models.schemas import MacroSnapshot, StockMetrics, StockPick
from stock_autopilot.universe import brand_cfg


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def volatility_fit_score(vol: float, target_min: float, target_max: float) -> float:
    """Prefer moderate volatility aligned with 12-15% annual return profile (~15-25% vol)."""
    ideal_low, ideal_high = 0.12, 0.28
    if ideal_low <= vol <= ideal_high:
        return 1.0
    if vol < ideal_low:
        return _clamp01(1 - (ideal_low - vol) / ideal_low)
    return _clamp01(1 - (vol - ideal_high) / 0.4)


def return_fit_score(ann_return: float, target_min: float, target_max: float) -> float:
    mid = (target_min + target_max) / 2
    if target_min <= ann_return <= target_max + 0.05:
        return 1.0
    if ann_return < target_min:
        return _clamp01(0.5 + ann_return / target_min * 0.5)
    if ann_return > target_max + 0.15:
        return _clamp01(1 - (ann_return - target_max) / 0.5)
    return 0.75


def momentum_score(metrics: StockMetrics) -> float:
    rsi_score = 1.0 - abs(metrics.rsi - 52) / 40
    mom = metrics.momentum_3m * 0.4 + metrics.momentum_12m * 0.6
    mom_score = _clamp01(0.5 + mom)
    return _clamp01(rsi_score * 0.4 + mom_score * 0.6)


def valuation_score(metrics: StockMetrics) -> float:
    if metrics.pe_ratio is None:
        return 0.5
    if 8 <= metrics.pe_ratio <= 35:
        return 1.0
    if metrics.pe_ratio < 8:
        return 0.7
    return _clamp01(1 - (metrics.pe_ratio - 35) / 50)


def macro_alignment_score(metrics: StockMetrics, macro: MacroSnapshot) -> float:
    defensive_sectors = {"Healthcare", "Utilities", "Consumer Defensive", "Consumer Staples"}
    growth_sectors = {"Technology", "Communication Services", "Consumer Cyclical"}

    if macro.regime.startswith("Risk-Off"):
        if metrics.sector in defensive_sectors:
            return 0.9
        if metrics.sector in growth_sectors and metrics.volatility > 0.35:
            return 0.3
        return 0.55
    if macro.regime.startswith("Risk-On"):
        if metrics.sector in growth_sectors and metrics.momentum_3m > 0:
            return 0.9
        return 0.6
    return 0.65


def news_score(sentiment: float) -> float:
    return _clamp01(0.5 + sentiment * 0.5)


def score_stock(
    metrics: StockMetrics,
    macro: MacroSnapshot,
    news_sentiment: float,
    weights: dict[str, float],
    target_min: float | None = None,
    target_max: float | None = None,
) -> float:
    if target_min is None or target_max is None:
        from stock_autopilot.investor_profile import get_return_target

        target_min, target_max = get_return_target()

    components = {
        "momentum": momentum_score(metrics),
        "valuation": valuation_score(metrics),
        "volatility_fit": volatility_fit_score(metrics.volatility, target_min, target_max),
        "news_sentiment": news_score(news_sentiment),
        "macro_alignment": macro_alignment_score(metrics, macro),
    }
    ret_fit = return_fit_score(metrics.annualized_return, target_min, target_max)

    total_w = sum(weights.values())
    score = sum(components[k] * weights.get(k, 0) for k in components) / total_w
    score = score * 0.85 + ret_fit * 0.15
    return round(score, 4)


def build_rationale(
    metrics: StockMetrics,
    macro: MacroSnapshot,
    news_sentiment: float,
    themes: list[str],
) -> str:
    parts = [
        f"12M annualized return {metrics.annualized_return*100:.1f}% (vol {metrics.volatility*100:.1f}%).",
        f"RSI {metrics.rsi:.0f}, 3M momentum {metrics.momentum_3m*100:+.1f}%.",
        f"Macro regime: {macro.regime}.",
    ]
    if news_sentiment > 0.15:
        parts.append("Recent headlines skew positive.")
    elif news_sentiment < -0.15:
        parts.append("Recent headlines skew cautious — verify before acting.")
    if "partnership" in themes or "m_and_a" in themes:
        parts.append("News flow includes partnerships/M&A themes.")
    return " ".join(parts)


def rank_candidates(
    metrics_list: list[StockMetrics],
    macro: MacroSnapshot,
    news_map: dict[str, tuple[float, list[str], list[str]]],
    weights: dict[str, float],
    daily_picks: int,
    max_per_region: int,
    max_per_sector: int,
    min_avg_volume: float,
) -> list[StockPick]:
    scored: list[tuple[float, StockMetrics, float, list[str], list[str]]] = []
    from stock_autopilot.investor_profile import get_return_target

    tmin, tmax = get_return_target()

    for m in metrics_list:
        if m.avg_volume < min_avg_volume:
            continue
        sent, _, themes = news_map.get(m.symbol, (0.0, [], []))
        s = score_stock(m, macro, sent, weights)
        _, highlights, themes = news_map.get(m.symbol, (sent, [], themes))
        scored.append((s, m, sent, highlights, themes))

    scored.sort(key=lambda x: x[0], reverse=True)

    picks: list[StockPick] = []
    region_count: dict[str, int] = {}
    sector_count: dict[str, int] = {}

    for score, m, sent, highlights, themes in scored:
        if len(picks) >= daily_picks:
            break
        if region_count.get(m.region, 0) >= max_per_region:
            continue
        if sector_count.get(m.sector, 0) >= max_per_sector:
            continue

        region_count[m.region] = region_count.get(m.region, 0) + 1
        sector_count[m.sector] = sector_count.get(m.sector, 0) + 1

        est_return = min(tmax, max(tmin, m.annualized_return * 0.6 + 0.06))

        note = build_research_note(m, macro, score, sent, themes, highlights)
        note_text = format_research_note_text(note, m.symbol, m.name, m.sector)

        picks.append(
            StockPick(
                symbol=m.symbol,
                name=m.name,
                region=m.region,
                sector=m.sector,
                score=score,
                annualized_return_est=round(est_return, 4),
                rationale=build_rationale(m, macro, sent, themes),
                news_highlights=highlights,
                themes=themes,
                risk_note=f"Illustrative {brand_cfg()['brand_name']} research — not investment advice. Past performance ≠ future results.",
                research_note=note,
                research_note_text=note_text,
            )
        )

    return picks
