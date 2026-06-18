from __future__ import annotations

from stock_autopilot.config import settings
from stock_autopilot.db import get_app_setting, set_app_setting
from stock_autopilot.universe import load_config

_SETTING_MIN = "target_return_min"
_SETTING_MAX = "target_return_max"
_SETTING_RANKED_MIN = "last_ranked_target_min"
_SETTING_RANKED_MAX = "last_ranked_target_max"


def _from_config() -> tuple[float, float]:
    cfg = load_config()
    profile = cfg.get("investor_profile") or {}
    if profile.get("target_min_pct") is not None and profile.get("target_max_pct") is not None:
        return float(profile["target_min_pct"]) / 100, float(profile["target_max_pct"]) / 100
    if profile.get("target_pct") is not None:
        mid = float(profile["target_pct"])
        width = float(profile.get("band_width_pct", 3))
        return (mid - width) / 100, (mid + width) / 100
    return settings.target_return_min, settings.target_return_max


def get_return_target() -> tuple[float, float]:
    """Active annual return band as decimals (e.g. 0.12, 0.15)."""
    stored_min = get_app_setting(_SETTING_MIN)
    stored_max = get_app_setting(_SETTING_MAX)
    if stored_min is not None and stored_max is not None:
        return float(stored_min), float(stored_max)
    return _from_config()


def set_return_target(min_pct: float, max_pct: float) -> dict:
    if min_pct <= 0 or max_pct <= 0:
        raise ValueError("Target percentages must be positive")
    if min_pct > max_pct:
        raise ValueError("Minimum target cannot exceed maximum")
    if max_pct > 100:
        raise ValueError("Target cannot exceed 100%")
    set_app_setting(_SETTING_MIN, str(min_pct / 100))
    set_app_setting(_SETTING_MAX, str(max_pct / 100))
    out = get_return_target_pct()
    out["picks_synced"] = False
    out["message"] = "Target saved. Re-rank picks to apply your new profile."
    return out


def mark_picks_ranked_for_target() -> None:
    tmin, tmax = get_return_target()
    set_app_setting(_SETTING_RANKED_MIN, str(tmin))
    set_app_setting(_SETTING_RANKED_MAX, str(tmax))


def picks_synced_with_target() -> bool:
    ranked_min = get_app_setting(_SETTING_RANKED_MIN)
    ranked_max = get_app_setting(_SETTING_RANKED_MAX)
    if ranked_min is None or ranked_max is None:
        return False
    tmin, tmax = get_return_target()
    return abs(float(ranked_min) - tmin) < 0.0001 and abs(float(ranked_max) - tmax) < 0.0001


def get_return_target_pct() -> dict:
    tmin, tmax = get_return_target()
    synced = picks_synced_with_target()
    return {
        "target_min_pct": round(tmin * 100, 1),
        "target_max_pct": round(tmax * 100, 1),
        "target_min": tmin,
        "target_max": tmax,
        "label": f"{round(tmin * 100):g}–{round(tmax * 100):g}% / yr",
        "picks_synced": synced,
        "needs_rerank": not synced,
    }
