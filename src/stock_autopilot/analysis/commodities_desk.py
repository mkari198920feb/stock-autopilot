from __future__ import annotations

from datetime import datetime, timezone

from stock_autopilot.collectors.commodities import CommodityRaw, fetch_commodities_universe
from stock_autopilot.models.schemas import (
    CommoditiesDeskSnapshot,
    CommodityCategoryBoard,
    CommodityDeskPick,
    CommodityQuote,
)
from stock_autopilot.universe import brand_cfg


def _trend_bias(raw: CommodityRaw) -> tuple[str, str, str, str, int, str]:
    score = 0
    notes: list[str] = []

    if raw.change_1m_pct > 3:
        score += 2
        notes.append("1M momentum positive")
    elif raw.change_1m_pct < -3:
        score -= 2
        notes.append("1M momentum negative")

    if raw.ma_20 and raw.price > raw.ma_20:
        score += 1
        notes.append("above 20D MA")
    elif raw.ma_20 and raw.price < raw.ma_20:
        score -= 1
        notes.append("below 20D MA")

    if raw.rsi_14 > 65:
        score += 1
        notes.append(f"RSI {raw.rsi_14:.0f} — strong")
    elif raw.rsi_14 < 35:
        score -= 1
        notes.append(f"RSI {raw.rsi_14:.0f} — weak")

    if score >= 2:
        return "BULLISH", "bullish", "Up", "bullish", min(88, 55 + abs(int(raw.change_1m_pct))), "; ".join(notes[:2])
    if score <= -2:
        return "BEARISH", "bearish", "Down", "bearish", min(88, 55 + abs(int(raw.change_1m_pct))), "; ".join(notes[:2])
    return "NEUTRAL", "neutral", "Neutral", "neutral", 52, notes[0] if notes else "Range-bound"


def _to_quote(raw: CommodityRaw) -> CommodityQuote:
    bias_label, bias_class, trend, trend_class, conviction, note = _trend_bias(raw)
    dist_high = None
    if raw.week_52_high and raw.week_52_high > 0:
        dist_high = round((raw.price / raw.week_52_high - 1) * 100, 2)
    return CommodityQuote(
        symbol=raw.symbol,
        name=raw.name,
        category=raw.category_id,
        category_label=raw.category_label,
        unit=raw.unit,
        price=raw.price,
        change_1d_pct=raw.change_1d_pct,
        change_1w_pct=raw.change_1w_pct,
        change_1m_pct=raw.change_1m_pct,
        week_52_high=raw.week_52_high,
        week_52_low=raw.week_52_low,
        dist_from_52w_high_pct=dist_high,
        rsi_14=raw.rsi_14,
        ma_20=raw.ma_20,
        ma_50=raw.ma_50,
        trend=trend,
        trend_class=trend_class,
        bias_label=bias_label,
        bias_class=bias_class,
        conviction=conviction,
        desk_note=note,
    )


def _regime(quotes: list[CommodityQuote]) -> tuple[str, str]:
    by_sym = {q.symbol: q for q in quotes}
    gold = by_sym.get("GC=F")
    oil = by_sym.get("CL=F") or by_sym.get("BZ=F")
    copper = by_sym.get("HG=F")

    if oil and oil.change_1m_pct > 8:
        return "Energy Shock", "risk-off"
    if gold and gold.change_1m_pct > 5 and copper and copper.change_1m_pct < 0:
        return "Inflation Hedge / Risk-Off", "risk-off"
    if copper and copper.change_1m_pct > 4 and oil and oil.change_1m_pct > 0:
        return "Growth / Reflation", "risk-on"
    if gold and gold.change_1m_pct > 3:
        return "Safe-Haven Bid", "neutral"
    return "Mixed / Range-Bound", "neutral"


def _macro_read(quotes: list[CommodityQuote]) -> dict:
    by_sym = {q.symbol: q for q in quotes}
    gold = by_sym.get("GC=F")
    oil = by_sym.get("BZ=F") or by_sym.get("CL=F")
    copper = by_sym.get("HG=F")
    gas = by_sym.get("NG=F")
    brent_wti = None
    brent = by_sym.get("BZ=F")
    wti = by_sym.get("CL=F")
    if brent and wti and wti.price:
        brent_wti = round(brent.price - wti.price, 2)

    india_note = "Neutral for India macros"
    if oil:
        if oil.price > 85:
            india_note = "Bearish India — Brent >$85 (inflation/CAD pressure)"
        elif oil.price < 70:
            india_note = "Supportive India — Brent <$70 (OMCs/FMCG tailwind)"

    return {
        "gold_1m_pct": gold.change_1m_pct if gold else None,
        "oil_level": oil.price if oil else None,
        "oil_1m_pct": oil.change_1m_pct if oil else None,
        "copper_1m_pct": copper.change_1m_pct if copper else None,
        "nat_gas_1m_pct": gas.change_1m_pct if gas else None,
        "brent_wti_spread": brent_wti,
        "india_crude_read": india_note,
    }


def _commodity_pulse_text(quotes: list[CommodityQuote], regime: str) -> str:
    gainers = sorted(quotes, key=lambda q: q.change_1d_pct, reverse=True)[:2]
    losers = sorted(quotes, key=lambda q: q.change_1d_pct)[:2]
    g_txt = ", ".join(f"{q.name} {q.change_1d_pct:+.1f}%" for q in gainers)
    l_txt = ", ".join(f"{q.name} {q.change_1d_pct:+.1f}%" for q in losers)
    return f"{regime} · Leaders: {g_txt} · Laggards: {l_txt}"


def _build_picks(quotes: list[CommodityQuote], n: int) -> list[CommodityDeskPick]:
    ranked = sorted(
        quotes,
        key=lambda q: (q.conviction, abs(q.change_1m_pct)),
        reverse=True,
    )
    picks: list[CommodityDeskPick] = []
    seen_cat: set[str] = set()
    for q in ranked:
        if q.category in seen_cat and len(picks) >= n // 2:
            continue
        thesis = (
            f"{q.name} {q.bias_label.lower()} — {q.desk_note}. "
            f"1M {q.change_1m_pct:+.1f}%, RSI {q.rsi_14:.0f}."
        )
        risk = "Volatility spike on macro headlines" if q.category == "energy" else "Mean-reversion after extended move"
        if q.rsi_14 > 70:
            risk = "Overbought — size small or wait for pullback"
        elif q.rsi_14 < 30:
            risk = "Oversold bounce possible — confirm trend first"
        picks.append(
            CommodityDeskPick(
                rank=len(picks) + 1,
                symbol=q.symbol,
                name=q.name,
                category=q.category_label,
                price=q.price,
                unit=q.unit,
                change_1d_pct=q.change_1d_pct,
                change_1m_pct=q.change_1m_pct,
                bias_label=q.bias_label,
                bias_class=q.bias_class,
                conviction=q.conviction,
                thesis=thesis,
                risk=risk,
            )
        )
        seen_cat.add(q.category)
        if len(picks) >= n:
            break
    return picks


def _tomorrow_setup(regime: str, macro: dict) -> str:
    bits = [f"Regime: {regime}."]
    if macro.get("india_crude_read"):
        bits.append(macro["india_crude_read"] + ".")
    if macro.get("brent_wti_spread") is not None:
        bits.append(f"Brent-WTI spread ${macro['brent_wti_spread']:.2f}.")
    bits.append("Watch USD, US 10Y, and China PMIs for cross-asset commodity direction.")
    return " ".join(bits)


def build_commodities_desk(cfg: dict) -> CommoditiesDeskSnapshot:
    desk_cfg = cfg.get("commodities_desk", {})
    categories_cfg = desk_cfg.get("categories") or {}
    raw_rows = fetch_commodities_universe(categories_cfg)
    quotes = [_to_quote(r) for r in raw_rows]

    by_cat: dict[str, list[CommodityQuote]] = {}
    for q in quotes:
        by_cat.setdefault(q.category, []).append(q)

    category_boards: list[CommodityCategoryBoard] = []
    for cat_id, cat in categories_cfg.items():
        items = by_cat.get(cat_id, [])
        if not items:
            continue
        avg_1d = sum(i.change_1d_pct for i in items) / len(items)
        avg_1w = sum(i.change_1w_pct for i in items) / len(items)
        top = max(items, key=lambda x: x.change_1d_pct)
        category_boards.append(
            CommodityCategoryBoard(
                category_id=cat_id,
                label=cat.get("label", cat_id),
                change_1d_pct=round(avg_1d, 2),
                change_1w_pct=round(avg_1w, 2),
                quotes=items,
                top_mover=f"{top.name} {top.change_1d_pct:+.1f}%",
                setup_note=f"Watch {top.name} as category bellwether.",
            )
        )

    regime, regime_class = _regime(quotes)
    macro = _macro_read(quotes)
    pulse = _commodity_pulse_text(quotes, regime)
    brand = brand_cfg().get("brand_name", "LUMIQ")

    return CommoditiesDeskSnapshot(
        desk_id=datetime.now(timezone.utc).strftime("%Y%m%d") + "-cmdty-" + datetime.now(timezone.utc).strftime("%H%M"),
        captured_at=datetime.now(timezone.utc),
        opening_statement=(
            f"{brand} Commodities Desk tracks precious metals, energy, industrial metals, "
            "agriculture futures, and ETF proxies — with macro cross-reads for India crude "
            "and global risk regime."
        ),
        regime=regime,
        regime_class=regime_class,
        commodity_pulse=pulse,
        macro_read=macro,
        categories=category_boards,
        top_gainers=sorted(quotes, key=lambda q: q.change_1d_pct, reverse=True)[:5],
        top_losers=sorted(quotes, key=lambda q: q.change_1d_pct)[:5],
        desk_picks=_build_picks(quotes, desk_cfg.get("desk_picks", 6)),
        tomorrow_setup=_tomorrow_setup(regime, macro),
        disclaimer=desk_cfg.get(
            "disclaimer",
            "Futures and commodities are volatile. Research only — not trading advice.",
        ),
    )
