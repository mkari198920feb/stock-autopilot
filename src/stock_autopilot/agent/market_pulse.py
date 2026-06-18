from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.market_pulse import build_market_pulse_snapshot
from stock_autopilot.db import init_db, save_market_pulse
from stock_autopilot.models.schemas import MarketPulseSnapshot


def run_market_pulse() -> MarketPulseSnapshot:
    init_db()
    snap = build_market_pulse_snapshot()
    snap.pulse_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") + "-pulse-" + uuid.uuid4().hex[:6]
    save_market_pulse(snap)
    return snap
