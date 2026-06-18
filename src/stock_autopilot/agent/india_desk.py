from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.india_advisory import build_bond_notes, build_fd_notes, build_mutual_fund_notes
from stock_autopilot.analysis.india_research import rank_india_equities
from stock_autopilot.collectors.india_macro import fetch_india_macro
from stock_autopilot.collectors.india_market import fetch_india_universe
from stock_autopilot.db import init_db, save_india_desk
from stock_autopilot.analysis.outcomes import record_india_picks, resolve_due_outcomes
from stock_autopilot.models.schemas import IndiaDeskSnapshot
from stock_autopilot.universe import brand_cfg, load_config


def _opening_statement() -> str:
    name = brand_cfg().get("brand_name", "Uptick Alpha")
    return (
        f"Namaste. {name} India Desk is active — NSE/BSE equities, mutual funds, "
        "bonds, and FD rates with risk tiering and Indian tax treatment on every idea."
    )


OPENING = _opening_statement()


def run_india_desk() -> IndiaDeskSnapshot:
    init_db()
    cfg = load_config()
    india_cfg = cfg.get("india_desk", {})
    macro = fetch_india_macro(cfg)
    metrics = fetch_india_universe(cfg)
    weights = india_cfg.get("scoring_weights") or cfg.get("scoring", {}).get("weights", {})
    bse_map = india_cfg.get("bse_codes") or {}

    equities = rank_india_equities(
        metrics,
        macro,
        weights,
        bse_map,
        daily_picks=india_cfg.get("daily_picks", 6),
        max_per_sector=india_cfg.get("max_per_sector", 2),
    )

    snapshot = IndiaDeskSnapshot(
        desk_id=datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8],
        captured_at=datetime.now(timezone.utc),
        opening_statement=OPENING,
        macro=macro,
        equities=equities,
        mutual_funds=build_mutual_fund_notes(cfg),
        bonds=build_bond_notes(cfg),
        fixed_deposits=build_fd_notes(cfg),
        disclaimer=india_cfg.get(
            "disclaimer",
            "Research publisher only. Consult your SEBI-registered financial advisor before investing.",
        ),
    )
    save_india_desk(snapshot)
    try:
        record_india_picks(snapshot)
        resolve_due_outcomes()
        from stock_autopilot.investor_profile import mark_picks_ranked_for_target

        mark_picks_ranked_for_target()
    except Exception:
        pass
    return snapshot
