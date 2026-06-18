from __future__ import annotations

from stock_autopilot.analysis.research_notes import assign_risk_tier, build_research_note
from stock_autopilot.analysis.scorer import score_stock
from stock_autopilot.collectors.news import aggregate_news_sentiment, fetch_news_for_symbol
from stock_autopilot.models.schemas import MacroSnapshot, RegionalBoard, RegionalPickRow, StockMetrics


def _rating(score: float, tier: int) -> str:
    if score >= 0.72:
        return "BUY" if tier <= 3 else "ACCUMULATE"
    if score >= 0.58:
        return "ACCUMULATE" if tier <= 3 else "BUY"
    if score >= 0.48:
        return "HOLD"
    return "REDUCE"


def _row_from_metrics(
    rank: int,
    m: StockMetrics,
    score: float,
    macro: MacroSnapshot,
    sent: float,
    themes: list[str],
    exchange: str,
    country: str,
) -> RegionalPickRow:
    tier = assign_risk_tier(m, sent, themes)
    note = build_research_note(m, macro, score, sent, themes, [])
    target = note.price_target or m.price * 1.12
    upside = note.upside_pct or round((target / m.price - 1) * 100, 1)
    thesis = note.thesis[0] if note.thesis else m.sector
    return RegionalPickRow(
        rank=rank,
        symbol=m.symbol,
        name=m.name,
        exchange=exchange,
        country=country,
        risk_tier=tier,
        rating=_rating(score, tier),
        cmp=round(m.price, 2),
        target=round(target, 2),
        upside_pct=round(upside, 1),
        score=round(score, 3),
        desk_note=note.desk_comment or thesis,
        thesis_line=thesis[:120],
    )


def build_regional_board(
    market_id: str,
    market_cfg: dict,
    metrics_list: list[StockMetrics],
    macro: MacroSnapshot,
    news_map: dict,
    weights: dict,
    picks_n: int = 5,
    avoids_n: int = 2,
) -> RegionalBoard:
    scored: list[tuple[float, StockMetrics, float, list[str]]] = []
    for m in metrics_list:
        sent, _, themes = news_map.get(m.symbol, (0.0, [], []))
        s = score_stock(m, macro, sent, weights)
        scored.append((s, m, sent, themes))
    scored.sort(key=lambda x: x[0], reverse=True)

    picks: list[RegionalPickRow] = []
    for i, (s, m, sent, themes) in enumerate(scored[:picks_n], 1):
        picks.append(
            _row_from_metrics(
                i, m, s, macro, sent, themes,
                market_cfg.get("exchange", ""),
                market_cfg.get("country", ""),
            )
        )

    avoids: list[RegionalPickRow] = []
    for i, (s, m, sent, themes) in enumerate(scored[-avoids_n:], 1):
        row = _row_from_metrics(
            i, m, s, macro, sent, themes,
            market_cfg.get("exchange", ""),
            market_cfg.get("country", ""),
        )
        row.rating = "REDUCE" if s < 0.45 else "SELL"
        avoids.append(row)

    return RegionalBoard(
        market_id=market_id,
        label=market_cfg.get("label", market_id),
        exchange=market_cfg.get("exchange", ""),
        country=market_cfg.get("country", ""),
        theme=market_cfg.get("theme", ""),
        top_risk=market_cfg.get("top_risk", "Macro uncertainty"),
        macro_pulse={
            "theme": market_cfg.get("theme", ""),
            "top_risk": market_cfg.get("top_risk", ""),
            "country": market_cfg.get("country", ""),
        },
        picks=picks,
        avoids=avoids,
    )


def build_all_regional_boards(
    market_metrics: dict[str, list[StockMetrics]],
    markets_cfg: dict[str, dict],
    macro: MacroSnapshot,
    weights: dict,
    picks_n: int,
    avoids_n: int,
) -> list[RegionalBoard]:
    boards: list[RegionalBoard] = []
    all_syms = [m.symbol for ms in market_metrics.values() for m in ms]
    news_map: dict[str, tuple[float, list[str], list[str]]] = {}
    for s in all_syms[:40]:
        news_map[s] = aggregate_news_sentiment(fetch_news_for_symbol(s))
    for market_id, metrics in market_metrics.items():
        if not metrics:
            continue
        cfg = markets_cfg.get(market_id, {})
        boards.append(
            build_regional_board(
                market_id, cfg, metrics, macro, news_map, weights, picks_n, avoids_n
            )
        )
    return boards


def flatten_top_global(boards: list[RegionalBoard], top_n: int = 10) -> list[RegionalPickRow]:
    rows: list[RegionalPickRow] = []
    for b in boards:
        rows.extend(b.picks)
    rows.sort(key=lambda r: r.score, reverse=True)
    out: list[RegionalPickRow] = []
    for i, r in enumerate(rows[:top_n], 1):
        out.append(r.model_copy(update={"rank": i}))
    return out
