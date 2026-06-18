from __future__ import annotations

from stock_autopilot.analysis.scorer import build_rationale, score_stock
from stock_autopilot.models.schemas import MacroSnapshot, ModelPortfolio, ModelPortfolioHolding, StockMetrics


def _merge_weights(base: dict[str, float], bias: dict[str, float]) -> dict[str, float]:
    merged = dict(base)
    for key, value in bias.items():
        merged[key] = value
    return merged


def _score_all(
    metrics_list: list[StockMetrics],
    macro: MacroSnapshot,
    news_map: dict[str, tuple[float, list[str], list[str]]],
    weights: dict[str, float],
    min_avg_volume: float,
) -> list[tuple[float, StockMetrics, float, list[str], list[str]]]:
    scored: list[tuple[float, StockMetrics, float, list[str], list[str]]] = []
    for m in metrics_list:
        if m.avg_volume < min_avg_volume:
            continue
        sent, highlights, themes = news_map.get(m.symbol, (0.0, [], []))
        s = score_stock(m, macro, sent, weights)
        scored.append((s, m, sent, highlights, themes))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _regime_cash_pct(macro: MacroSnapshot, base_cash: float) -> float:
    if macro.regime.startswith("Risk-Off"):
        return min(0.25, base_cash + 0.10)
    if macro.regime.startswith("Risk-On"):
        return max(0.0, base_cash - 0.05)
    return base_cash


def _assign_weights(
    entries: list[tuple[float, StockMetrics, float, list[str], list[str]]],
    macro: MacroSnapshot,
    max_single_weight: float,
    cash_pct: float,
) -> list[ModelPortfolioHolding]:
    if not entries:
        return []

    equity_budget = 1.0 - cash_pct
    raw = [score for score, _, _, _, _ in entries]
    total = sum(raw) or 1.0
    weights = [score / total * equity_budget for score in raw]

    capped = [min(w, max_single_weight) for w in weights]
    cap_total = sum(capped) or 1.0
    scale = equity_budget / cap_total
    weights = [round(w * scale, 4) for w in capped]

    from stock_autopilot.investor_profile import get_return_target

    tmin, tmax = get_return_target()
    holdings: list[ModelPortfolioHolding] = []
    for (score, metrics, sent, _, themes), weight in zip(entries, weights):
        holdings.append(
            ModelPortfolioHolding(
                symbol=metrics.symbol,
                name=metrics.name,
                region=metrics.region,
                sector=metrics.sector,
                weight=weight,
                score=score,
                annualized_return_est=round(
                    min(tmax, max(tmin, metrics.annualized_return * 0.6 + 0.06)),
                    4,
                ),
                rationale=build_rationale(metrics, macro, sent, themes),
            )
        )
    return holdings


def _filter_for_model(
    scored: list[tuple[float, StockMetrics, float, list[str], list[str]]],
    model_cfg: dict,
    macro: MacroSnapshot,
) -> list[tuple[float, StockMetrics, float, list[str], list[str]]]:
    max_vol = model_cfg.get("max_volatility")
    min_mom = model_cfg.get("min_momentum_3m")
    prefer_sectors = set(model_cfg.get("prefer_sectors") or [])
    prefer_symbols = set(model_cfg.get("prefer_symbols") or [])
    max_per_sector = model_cfg.get("max_per_sector", 2)
    max_per_region = model_cfg.get("max_per_region", 3)
    holdings = model_cfg.get("holdings", 8)

    selected: list[tuple[float, StockMetrics, float, list[str], list[str]]] = []
    sector_count: dict[str, int] = {}
    region_count: dict[str, int] = {}

    for row in scored:
        score, metrics, _, _, _ = row
        if len(selected) >= holdings:
            break
        if max_vol is not None and metrics.volatility > max_vol:
            continue
        if min_mom is not None and metrics.momentum_3m < min_mom:
            continue
        if prefer_sectors and metrics.sector not in prefer_sectors and metrics.symbol not in prefer_symbols:
            continue
        if sector_count.get(metrics.sector, 0) >= max_per_sector:
            continue
        if region_count.get(metrics.region, 0) >= max_per_region:
            continue

        sector_count[metrics.sector] = sector_count.get(metrics.sector, 0) + 1
        region_count[metrics.region] = region_count.get(metrics.region, 0) + 1
        selected.append(row)

    if len(selected) < min(3, holdings):
        for row in scored:
            if len(selected) >= holdings:
                break
            score, metrics, _, _, _ = row
            if any(m.symbol == metrics.symbol for _, m, _, _, _ in selected):
                continue
            if sector_count.get(metrics.sector, 0) >= max_per_sector:
                continue
            if region_count.get(metrics.region, 0) >= max_per_region:
                continue
            sector_count[metrics.sector] = sector_count.get(metrics.sector, 0) + 1
            region_count[metrics.region] = region_count.get(metrics.region, 0) + 1
            selected.append(row)

    return selected


def build_model_portfolios(
    metrics_list: list[StockMetrics],
    macro: MacroSnapshot,
    news_map: dict[str, tuple[float, list[str], list[str]]],
    cfg: dict,
    min_avg_volume: float,
) -> list[ModelPortfolio]:
    portfolio_cfg = cfg.get("model_portfolios", {})
    models = portfolio_cfg.get("models") or {}
    if not models:
        return []

    base_weights = cfg.get("scoring", {}).get("weights", {})
    benchmark = portfolio_cfg.get("benchmark", "SPY")
    publisher_note = portfolio_cfg.get(
        "disclaimer",
        "Illustrative model portfolio for research only. Not personalized advice. "
        "Friends self-direct trades in their own accounts.",
    )

    portfolios: list[ModelPortfolio] = []
    for model_id, model_cfg in models.items():
        weights = _merge_weights(base_weights, model_cfg.get("scoring_bias") or {})
        scored = _score_all(metrics_list, macro, news_map, weights, min_avg_volume)
        selected = _filter_for_model(scored, model_cfg, macro)
        cash_pct = _regime_cash_pct(macro, float(model_cfg.get("base_cash_pct", 0.05)))
        holdings = _assign_weights(
            selected,
            macro,
            float(model_cfg.get("max_single_weight", 0.15)),
            cash_pct,
        )

        portfolios.append(
            ModelPortfolio(
                model_id=model_id,
                label=model_cfg.get("label", model_id.title()),
                description=model_cfg.get("description", ""),
                benchmark=benchmark,
                cash_pct=round(cash_pct, 4),
                holdings=holdings,
                disclaimer=publisher_note,
            )
        )

    return portfolios
