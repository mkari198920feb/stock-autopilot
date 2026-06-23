from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stock_autopilot.agent.commodities_desk import run_commodities_desk
from stock_autopilot.agent.crypto_pulse import run_crypto_pulse
from stock_autopilot.agent.global_desk import run_global_desk
from stock_autopilot.agent.india_desk import run_india_desk
from stock_autopilot.agent.market_pulse import run_market_pulse
from stock_autopilot.agent.orchestrator import run_autopilot
from stock_autopilot.analysis.crypto_research import build_crypto_research_note
from stock_autopilot.analysis.desk_stats import get_desk_activity
from stock_autopilot.api.auth import enforce_request_auth
from stock_autopilot.api.helpers import freshness_meta
from stock_autopilot.config import settings
from stock_autopilot.investor_profile import get_return_target_pct
from stock_autopilot.collectors.cache import init_cache
from stock_autopilot.collectors.data_health import run_data_health_check
from stock_autopilot.db import (
    get_latest_commodities_desk_dict,
    get_latest_crypto_pulse_dict,
    get_latest_global_desk_dict,
    get_latest_india_desk_dict,
    get_latest_market_pulse_dict,
    get_latest_run,
    init_db,
    list_runs,
)
from stock_autopilot.scheduler.jobs import start_scheduler
from stock_autopilot.universe import load_config

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _regime_class(regime: str) -> str:
    if "Off" in regime:
        return "risk-off"
    if "On" in regime:
        return "risk-on"
    return "neutral"


def _dashboard_context(latest: dict | None, runs: list[dict]) -> dict:
    cfg = load_config()
    apex = cfg.get("apex", {})
    band = get_return_target_pct()
    ctx: dict = {
        "latest": latest,
        "runs": runs,
        "target_min": int(band["target_min_pct"]),
        "target_max": int(band["target_max_pct"]),
        "target_min_pct": band["target_min_pct"],
        "target_max_pct": band["target_max_pct"],
        "target_label": band["label"],
        "needs_rerank": band.get("needs_rerank", False),
        "picks_synced": band.get("picks_synced", False),
        "autopilot_time": f"{settings.autopilot_hour:02d}:{settings.autopilot_minute:02d} UTC",
        "region_stats": {},
        "sector_stats": {},
        "avg_score": 0,
        "regime_class": "neutral",
        "risk_pct": 50,
        "firm_name": apex.get("firm_name", "LUMIQ Research Desk"),
        "firm_role": apex.get("role", "Chief Investment Strategist · Equity Research"),
        "firm_tagline": apex.get("tagline", "Institutional-grade equity research"),
        "brand_name": apex.get("brand_name", "LUMIQ"),
        "brand_short": apex.get("brand_short", "◈"),
        "brand_tagline": apex.get("brand_tagline", "Global markets · Research autopilot"),
        "powered_by": apex.get("powered_by", "LUMIQ"),
        "email_subject_prefix": cfg.get("notifications", {}).get("email", {}).get("subject_prefix", "LUMIQ Daily"),
        "crypto_pulse": get_latest_crypto_pulse_dict(),
        "commodities_desk": get_latest_commodities_desk_dict(),
        "india_desk": get_latest_india_desk_dict(),
        "global_desk": get_latest_global_desk_dict(),
        "market_pulse": get_latest_market_pulse_dict(),
    }
    india = ctx["india_desk"]
    crypto = ctx["crypto_pulse"]
    gd = ctx["global_desk"]
    ctx["india_picks_today"] = (india.get("equities") or []) if india else []
    ctx["crypto_picks_today"] = []
    if crypto:
        for key in ("btc", "eth"):
            if crypto.get(key):
                ctx["crypto_picks_today"].append(crypto[key])
    ctx["global_picks_today"] = []
    if gd and gd.get("global_top_picks"):
        ctx["global_picks_today"] = gd["global_top_picks"]
    elif latest:
        ctx["global_picks_today"] = latest.get("picks") or []

    ctx["has_today_picks"] = bool(
        ctx["global_picks_today"] or ctx["india_picks_today"] or ctx["crypto_picks_today"]
    )
    ctx["desk_activity"] = get_desk_activity()
    ctx["fresh_global"] = freshness_meta(
        (gd.get("captured_at") if gd else None) or (latest["finished_at"] if latest else None),
        "global",
    )
    ctx["fresh_india"] = freshness_meta(
        india["captured_at"] if india else None, "india"
    )
    ctx["fresh_crypto"] = freshness_meta(
        crypto["captured_at"] if crypto else None, "crypto"
    )
    cmdty = ctx["commodities_desk"]
    ctx["fresh_commodities"] = freshness_meta(
        cmdty["captured_at"] if cmdty else None, "commodities"
    )
    mp = ctx["market_pulse"]
    ctx["fresh_pulse"] = freshness_meta(
        mp["captured_at"] if mp else None, "pulse"
    )
    ctx["fresh_advisory"] = freshness_meta(
        india["captured_at"] if india else None, "advisory"
    )
    ctx["next_scan_label"] = f"{settings.autopilot_hour:02d}:{settings.autopilot_minute:02d} UTC daily"
    ctx["dashboard_brief_url"] = "#morning-brief"
    ctx["executive_pulse"] = ""
    if gd and gd.get("opening_statement"):
        ctx["executive_pulse"] = gd["opening_statement"]
    elif latest and latest.get("macro", {}).get("summary"):
        ctx["executive_pulse"] = latest["macro"]["summary"]
    ctx["email_desk_summary"] = "Global · India · Crypto · Commodities · Equity notes · Model books"
    ctx["auth_enabled"] = cfg.get("auth", {}).get("enabled", False)
    ctx["data_health"] = run_data_health_check(cfg)
    ctx["today_picks_date"] = ""
    if gd and gd.get("captured_at"):
        ctx["today_picks_date"] = gd["captured_at"][:10]
    elif latest and latest.get("finished_at"):
        ctx["today_picks_date"] = latest["finished_at"][:10]
    elif india and india.get("captured_at"):
        ctx["today_picks_date"] = india["captured_at"][:10]
    elif crypto and crypto.get("captured_at"):
        ctx["today_picks_date"] = crypto["captured_at"][:10]

    if not latest:
        return ctx

    ctx["regime_class"] = _regime_class(latest["macro"]["regime"])
    ctx["risk_pct"] = int(float(latest["macro"]["risk_score"]) * 100)

    picks = latest.get("picks") or []
    if picks:
        ctx["avg_score"] = round(sum(p["score"] for p in picks) / len(picks) * 100)
        for p in picks:
            ctx["region_stats"][p["region"]] = ctx["region_stats"].get(p["region"], 0) + 1
            ctx["sector_stats"][p["sector"]] = ctx["sector_stats"].get(p["sector"], 0) + 1

    return ctx

app = FastAPI(title="LUMIQ", version="0.2.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def lumiq_auth_middleware(request: Request, call_next):
    enforce_request_auth(request)
    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    init_cache()
    start_scheduler()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    latest = get_latest_run()
    runs = list_runs(10)
    ctx = _dashboard_context(latest, runs)
    ctx["request"] = request
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/email-preview", response_class=HTMLResponse)
async def email_preview():
    from stock_autopilot.notifications.email import build_digest_html, load_digest_bundle

    try:
        bundle = load_digest_bundle()
    except ValueError:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>No digest data yet</h2><p>Run a scan first, then preview the email friends receive.</p>"
            "</body></html>",
            status_code=404,
        )
    cfg = load_config()
    url = settings.dashboard_url or cfg.get("notifications", {}).get("email", {}).get("dashboard_url", "")
    return HTMLResponse(build_digest_html(bundle, url, cfg))


@app.get("/api/latest")
async def api_latest():
    data = get_latest_run()
    if not data:
        return JSONResponse({"status": "no_runs"}, status_code=404)
    return data


@app.get("/api/runs")
async def api_runs():
    return list_runs(30)


@app.post("/api/run-now")
async def api_run_now():
    result = run_autopilot()
    return result.model_dump(mode="json")


@app.get("/api/crypto-pulse")
async def api_crypto_pulse():
    data = get_latest_crypto_pulse_dict()
    if not data:
        return JSONResponse({"status": "no_data"}, status_code=404)
    return data


@app.post("/api/crypto-pulse/refresh")
async def api_crypto_pulse_refresh():
    try:
        pulse = run_crypto_pulse()
        return pulse.model_dump(mode="json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/commodities-desk")
async def api_commodities_desk():
    data = get_latest_commodities_desk_dict()
    if not data:
        return JSONResponse({"status": "no_data"}, status_code=404)
    return data


@app.post("/api/commodities-desk/refresh")
async def api_commodities_desk_refresh():
    try:
        snap = run_commodities_desk()
        return snap.model_dump(mode="json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/india-desk")
async def api_india_desk():
    data = get_latest_india_desk_dict()
    if not data:
        return JSONResponse({"status": "no_data"}, status_code=404)
    return data


@app.post("/api/india-desk/refresh")
async def api_india_desk_refresh():
    try:
        snap = run_india_desk()
        return snap.model_dump(mode="json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/global-desk")
async def api_global_desk():
    data = get_latest_global_desk_dict()
    if not data:
        return JSONResponse({"status": "no_data"}, status_code=404)
    return data


@app.post("/api/global-desk/refresh")
async def api_global_desk_refresh():
    try:
        snap = run_global_desk()
        return snap.model_dump(mode="json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/investor-profile")
async def api_investor_profile_get():
    return get_return_target_pct()


@app.put("/api/investor-profile")
async def api_investor_profile_put(request: Request):
    from stock_autopilot.investor_profile import get_return_target_pct, set_return_target

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    try:
        min_pct = float(body.get("target_min_pct", body.get("min_pct", 12)))
        max_pct = float(body.get("target_max_pct", body.get("max_pct", 15)))
        result = set_return_target(min_pct, max_pct)
        if body.get("rerank"):
            run_global_desk()
            run_india_desk()
            result = get_return_target_pct()
            result["reranked"] = True
            result["message"] = "Target saved and picks re-ranked."
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e), "rerank_failed": True}, status_code=500)


@app.post("/api/re-rank")
async def api_rerank(request: Request):
    """Re-score global and India desks with the current return target."""
    try:
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass
        run_global_desk()
        run_india_desk()
        if body.get("full"):
            run_autopilot()
        from stock_autopilot.investor_profile import get_return_target_pct

        out = get_return_target_pct()
        out["status"] = "ok"
        out["full_scan"] = bool(body.get("full"))
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/track-record")
async def api_track_record(refresh: bool = False):
    from stock_autopilot.analysis.outcomes import track_record_summary

    data = track_record_summary(include_live=True, force_live_refresh=refresh)
    return data


@app.get("/api/crypto-research/{symbol}")
async def api_crypto_research(symbol: str):
    note = build_crypto_research_note(symbol)
    if not note:
        return JSONResponse({"status": "not_found", "symbol": symbol.upper()}, status_code=404)
    return note


@app.get("/api/market-pulse")
async def api_market_pulse():
    data = get_latest_market_pulse_dict()
    if not data:
        return JSONResponse({"status": "no_data"}, status_code=404)
    return data


@app.post("/api/market-pulse/refresh")
async def api_market_pulse_refresh():
    try:
        snap = run_market_pulse()
        return snap.model_dump(mode="json")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/deep-intelligence/{symbol}")
async def api_deep_intelligence(symbol: str, context: str = ""):
    from stock_autopilot.analysis.deep_intelligence import build_deep_brief

    brief = build_deep_brief(symbol, trigger_context=context)
    if not brief:
        return JSONResponse({"status": "not_found", "symbol": symbol.upper()}, status_code=404)
    return brief.model_dump(mode="json")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return HTMLResponse(status_code=204)


@app.get("/api/data-health")
async def api_data_health(refresh: bool = False):
    return run_data_health_check(load_config(), force=refresh)


@app.get("/health")
async def health():
    cfg = load_config()
    dh = run_data_health_check(cfg)
    return {
        "status": "ok" if dh.get("status") != "critical" else "degraded",
        "scheduler": "active",
        "data_health": dh.get("status"),
        "data_probes_ok": f"{dh.get('ok_count')}/{dh.get('total')}",
        "auth_enabled": cfg.get("auth", {}).get("enabled", False),
    }
