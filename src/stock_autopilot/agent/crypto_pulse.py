from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.crypto_predictor import build_crypto_pulse
from stock_autopilot.collectors.crypto import fetch_crypto_context
from stock_autopilot.db import get_latest_crypto_pulse, init_db, save_crypto_pulse
from stock_autopilot.analysis.outcomes import record_crypto_pulse, resolve_due_outcomes
from stock_autopilot.models.schemas import CryptoPulseSnapshot


def run_crypto_pulse() -> CryptoPulseSnapshot:
    init_db()
    ctx = fetch_crypto_context()
    prior = get_latest_crypto_pulse()
    btc_streak = prior.btc_streak if prior else 0
    eth_streak = prior.eth_streak if prior else 0
    pulse = build_crypto_pulse(ctx, prior, btc_streak, eth_streak)
    pulse.pulse_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") + "-" + uuid.uuid4().hex[:6]
    save_crypto_pulse(pulse)
    try:
        record_crypto_pulse(pulse)
        resolve_due_outcomes()
    except Exception:
        pass
    return pulse
