from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.commodities_desk import build_commodities_desk
from stock_autopilot.db import init_db, save_commodities_desk
from stock_autopilot.analysis.outcomes import record_commodities_desk, resolve_due_outcomes
from stock_autopilot.models.schemas import CommoditiesDeskSnapshot
from stock_autopilot.universe import load_config


def run_commodities_desk() -> CommoditiesDeskSnapshot:
    init_db()
    cfg = load_config()
    snapshot = build_commodities_desk(cfg)
    snapshot.desk_id = datetime.now(timezone.utc).strftime("%Y%m%d") + "-cmdty-" + uuid.uuid4().hex[:8]
    save_commodities_desk(snapshot)
    try:
        record_commodities_desk(snapshot)
        resolve_due_outcomes()
    except Exception:
        pass
    return snapshot
