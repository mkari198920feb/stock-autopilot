from __future__ import annotations

from datetime import datetime, timezone, timedelta

from stock_autopilot.analysis.outcomes import track_record_summary
from stock_autopilot.db import (
    get_latest_commodities_desk_dict,
    get_latest_crypto_pulse_dict,
    get_latest_global_desk_dict,
    get_latest_india_desk_dict,
    get_latest_run,
    list_runs,
)


def get_desk_activity() -> dict:
    """Desk activity metrics for track-record / trust strip on dashboard."""
    runs = list_runs(30)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    runs_7d = 0
    for r in runs:
        try:
            fin = datetime.fromisoformat(r["finished_at"].replace("Z", "+00:00"))
            if fin.tzinfo is None:
                fin = fin.replace(tzinfo=timezone.utc)
            if fin >= week_ago:
                runs_7d += 1
        except ValueError:
            continue

    latest = get_latest_run()
    india = get_latest_india_desk_dict()
    crypto = get_latest_crypto_pulse_dict()
    commodities = get_latest_commodities_desk_dict()
    global_desk = get_latest_global_desk_dict()

    global_picks = len(global_desk.get("global_top_picks") or []) if global_desk else 0
    if not global_picks and latest:
        global_picks = len(latest.get("picks") or [])

    india_picks = len(india.get("equities") or []) if india else 0
    mf_count = len(india.get("mutual_funds") or []) if india else 0

    avg_score = 0
    if latest and latest.get("picks"):
        avg_score = round(sum(p["score"] for p in latest["picks"]) / len(latest["picks"]) * 100)

    spy_1m = None
    if latest:
        indicators = latest.get("macro", {}).get("indicators") or {}
        spy_1m = indicators.get("sp500_1m_pct")

    markets_live = sum(1 for x in (latest, india, crypto, commodities, global_desk) if x)

    top_global = []
    if global_desk and global_desk.get("global_top_picks"):
        for p in global_desk["global_top_picks"][:3]:
            top_global.append(p.get("symbol", ""))
    elif latest and latest.get("picks"):
        for p in latest["picks"][:3]:
            top_global.append(p["symbol"])

    track = track_record_summary(include_live=False)
    pending_snapshots = track.get("pending", 0)

    return {
        "runs_total": len(runs),
        "runs_7d": runs_7d,
        "global_picks": global_picks,
        "india_picks": india_picks,
        "mf_count": mf_count,
        "markets_live": markets_live,
        "avg_score": avg_score,
        "spy_1m_pct": spy_1m,
        "top_global_symbols": top_global,
        "has_history": len(runs) > 0,
        "track_record": track,
        "hit_rate_pct": track.get("hit_rate_pct"),
        "resolved_outcomes": track.get("total_resolved", 0),
        "pending_outcomes": pending_snapshots,
        "open_pick_count": None,
        "open_avg_return_pct": None,
        "open_win_rate_pct": None,
        "horizon_7d_hit_rate": track.get("horizon_7d", {}).get("hit_rate_pct"),
        "horizon_30d_hit_rate": track.get("horizon_30d", {}).get("hit_rate_pct"),
        "recent_outcomes": track.get("recent", []),
        "live_open_items": [],
        "live_track_loading": True,
    }
