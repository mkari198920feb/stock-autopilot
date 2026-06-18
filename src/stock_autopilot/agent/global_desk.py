from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.crypto_board import build_crypto_board, crypto_market_pulse
from stock_autopilot.analysis.regional_board import build_all_regional_boards, flatten_top_global
from stock_autopilot.collectors.global_signals import build_global_signal_stack, build_macro_ticker
from stock_autopilot.collectors.macro import analyze_global_conditions
from stock_autopilot.collectors.market import batch_fetch_metrics
from stock_autopilot.db import get_latest_commodities_desk, get_latest_crypto_pulse, get_latest_india_desk, init_db, save_global_desk
from stock_autopilot.analysis.outcomes import record_global_desk_picks, resolve_due_outcomes
from stock_autopilot.models.schemas import GlobalDeskSnapshot
from stock_autopilot.universe import brand_cfg, crypto_tier_universe, global_market_universe, load_config, load_global_desk_config


def _opening_statement() -> str:
    g = brand_cfg()["global_platform_name"]
    return (
        f"{g} is fully online. Every major region — US, Europe, Asia, Middle East, LatAm — "
        "plus a tiered crypto universe from Bitcoin to DeFi and tactical memes. "
        "Each session opens with a Global Signal Stack before any pick is published. "
        "Say 'Global Top Picks' on the dashboard or refresh the global desk."
    )


def run_global_desk() -> GlobalDeskSnapshot:
    init_db()
    cfg = load_config()
    gd_cfg = load_global_desk_config(cfg)
    markets = global_market_universe(cfg)
    crypto_tiers = crypto_tier_universe(cfg)

    macro = analyze_global_conditions(cfg.get("macro_symbols", {}))
    weights = cfg.get("scoring", {}).get("weights", {})

    market_metrics: dict[str, list] = {}
    for market_id, mcfg in markets.items():
        tickers = mcfg.get("tickers") or []
        if not tickers:
            continue
        region_label = mcfg.get("label", market_id)
        metrics = batch_fetch_metrics(
            tickers,
            {t: region_label for t in tickers},
            lookback_days=cfg.get("agent", {}).get("lookback_days", 252),
        )
        market_metrics[market_id] = metrics

    boards = build_all_regional_boards(
        market_metrics,
        markets,
        macro,
        weights,
        gd_cfg.get("picks_per_board", 5),
        gd_cfg.get("avoids_per_board", 2),
    )

    crypto_board = build_crypto_board(crypto_tiers)
    signal_stack = build_global_signal_stack(cfg)
    signal_stack["crypto_pulse"] = crypto_market_pulse(crypto_board)
    cmdty = get_latest_commodities_desk()
    if cmdty:
        signal_stack["commodity_pulse"] = cmdty.commodity_pulse
        signal_stack["commodities_regime"] = cmdty.regime

    india = get_latest_india_desk()
    india_macro = india.macro.model_dump() if india else None
    pulse = get_latest_crypto_pulse()
    btc_price = pulse.btc.current_price if pulse else None

    snapshot = GlobalDeskSnapshot(
        desk_id=datetime.now(timezone.utc).strftime("%Y%m%d") + "-global-" + uuid.uuid4().hex[:8],
        captured_at=datetime.now(timezone.utc),
        opening_statement=_opening_statement(),
        signal_stack=signal_stack,
        macro_ticker=build_macro_ticker(cfg, india_macro, btc_price),
        regional_boards=boards,
        crypto_board=crypto_board,
        global_top_picks=flatten_top_global(boards, gd_cfg.get("global_top_n", 10)),
        disclaimer="Research publisher only — verify FX, liquidity, and local access before investing.",
    )
    save_global_desk(snapshot)
    try:
        record_global_desk_picks(snapshot.desk_id, snapshot.captured_at, snapshot.global_top_picks)
        resolve_due_outcomes()
        from stock_autopilot.investor_profile import mark_picks_ranked_for_target

        mark_picks_ranked_for_target()
    except Exception:
        pass
    return snapshot
