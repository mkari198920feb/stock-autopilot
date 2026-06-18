from __future__ import annotations

from datetime import datetime, timezone


def freshness_meta(iso: str | None, kind: str = "global") -> dict:
    """Human-readable freshness label + stale flag for desk modules."""
    stale_after_min = {"global": 48 * 60, "india": 36 * 60, "crypto": 90, "commodities": 120, "pulse": 45, "advisory": 7 * 24 * 60}.get(
        kind, 24 * 60
    )
    if not iso:
        return {
            "label": "No data",
            "stale": True,
            "badge_class": "stale",
            "minutes": None,
        }

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"label": "Unknown", "stale": True, "badge_class": "stale", "minutes": None}

    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
    if minutes < 1:
        label = "Just now"
    elif minutes < 60:
        label = f"{minutes}m ago"
    elif minutes < 1440:
        label = f"{minutes // 60}h ago"
    else:
        label = f"{minutes // 1440}d ago"

    stale = minutes > stale_after_min
    badge_class = "stale" if stale else ("live" if minutes < 60 else "fresh")
    return {
        "label": label,
        "stale": stale,
        "badge_class": badge_class,
        "minutes": minutes,
    }
