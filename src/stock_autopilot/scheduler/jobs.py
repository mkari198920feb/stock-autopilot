from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from stock_autopilot.agent.crypto_pulse import run_crypto_pulse
from stock_autopilot.agent.orchestrator import run_autopilot
from stock_autopilot.config import settings
from stock_autopilot.db import init_db
from stock_autopilot.universe import load_config

_scheduler: BackgroundScheduler | None = None


def _maybe_run_global_desk() -> None:
    cfg = load_config()
    if not cfg.get("global_desk", {}).get("enabled", True):
        return
    from stock_autopilot.agent.global_desk import run_global_desk

    run_global_desk()


def _maybe_run_india_desk() -> None:
    cfg = load_config()
    if not cfg.get("india_desk", {}).get("enabled", True):
        return
    from stock_autopilot.agent.india_desk import run_india_desk

    run_india_desk()


def _resolve_outcomes() -> None:
    from stock_autopilot.analysis.outcomes import resolve_due_outcomes
    from stock_autopilot.collectors.cache import init_cache

    init_cache()
    resolve_due_outcomes()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    init_db()
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_autopilot,
        CronTrigger(hour=settings.autopilot_hour, minute=settings.autopilot_minute),
        id="daily_autopilot",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_crypto_pulse,
        CronTrigger(minute=5),
        id="hourly_crypto_pulse",
        replace_existing=True,
    )
    cfg = load_config()
    gd = cfg.get("global_desk", {})
    if gd.get("enabled", True):
        cron = gd.get("refresh_cron", "30 6 * * *")
        parts = cron.split()
        if len(parts) == 5:
            _scheduler.add_job(
                _maybe_run_global_desk,
                CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                ),
                id="daily_global_desk",
                replace_existing=True,
            )
    if cfg.get("india_desk", {}).get("enabled", True):
        _scheduler.add_job(
            _maybe_run_india_desk,
            CronTrigger(hour=settings.autopilot_hour, minute=max(0, settings.autopilot_minute - 5)),
            id="daily_india_desk",
            replace_existing=True,
        )
    _scheduler.add_job(
        _resolve_outcomes,
        CronTrigger(minute=20),
        id="hourly_resolve_outcomes",
        replace_existing=True,
    )
    _scheduler.start()

    try:
        run_crypto_pulse()
    except Exception:
        pass

    try:
        _maybe_run_india_desk()
    except Exception:
        pass

    try:
        _maybe_run_global_desk()
    except Exception:
        pass

    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
