from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from stock_autopilot.collectors.amfi import fetch_amfi_nav_map
from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.collectors.http_json import fetch_json
from stock_autopilot.universe import load_config

PROBE_SYMBOLS = [
    ("^GSPC", "S&P 500"),
    ("^NSEI", "Nifty 50"),
    ("GC=F", "Gold"),
    ("BZ=F", "Brent"),
    ("BTC-USD", "Bitcoin"),
]


def _probe_yahoo(symbol: str, *, retries: int = 2) -> dict:
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
            ok = not hist.empty and len(hist) >= 2
            price = float(hist["Close"].iloc[-1]) if ok else None
            bar_date = hist.index[-1].strftime("%Y-%m-%d") if ok else None
            stale_days = None
            if bar_date:
                bar_dt = datetime.strptime(bar_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                stale_days = (datetime.now(timezone.utc) - bar_dt).days
            return {
                "symbol": symbol,
                "ok": ok,
                "price": price,
                "bar_date": bar_date,
                "stale_days": stale_days,
            }
        except Exception as exc:
            last_err = exc
    return {"symbol": symbol, "ok": False, "error": str(last_err)[:80] if last_err else "unknown"}


def _probe_coingecko() -> dict:
    try:
        ping = fetch_json("https://api.coingecko.com/api/v3/ping", timeout=8, retries=2)
        ok = isinstance(ping, dict) and ping.get("gecko_says") is not None
        return {"source": "coingecko", "ok": ok, "label": "CoinGecko API"}
    except Exception as exc:
        return {"source": "coingecko", "ok": False, "label": "CoinGecko API", "error": str(exc)[:80]}


def _probe_amfi() -> dict:
    try:
        rows = fetch_amfi_nav_map(force=True, ttl=0)
        ok = len(rows) > 1000
        return {"source": "amfi", "ok": ok, "label": "AMFI NAV", "schemes": len(rows)}
    except Exception as exc:
        return {"source": "amfi", "ok": False, "label": "AMFI NAV", "error": str(exc)[:80]}


def run_data_health_check(cfg: dict | None = None, ttl: int = 900, force: bool = False) -> dict:
    cfg = cfg or load_config()
    key = "data_health:latest"
    if not force and ttl > 0:
        hit = cache_get_json(key)
        if isinstance(hit, dict) and hit.get("probes"):
            return hit

    extra = []
    for cat in (cfg.get("commodities_desk", {}).get("categories") or {}).values():
        for entry in (cat.get("symbols") or [])[:1]:
            sym = entry.get("symbol") if isinstance(entry, dict) else entry
            if sym:
                extra.append((sym, entry.get("name", sym) if isinstance(entry, dict) else sym))

    probes: list[dict] = []
    for sym, label in PROBE_SYMBOLS + extra[:3]:
        row = _probe_yahoo(sym)
        row["label"] = label
        row["source"] = "yfinance"
        probes.append(row)

    feeds = [_probe_coingecko(), _probe_amfi()]
    ok_count = sum(1 for p in probes if p.get("ok")) + sum(1 for f in feeds if f.get("ok"))
    total = len(probes) + len(feeds)
    status = "healthy" if ok_count == total else "degraded" if ok_count >= total // 2 else "critical"

    stale_yahoo = [p for p in probes if p.get("stale_days") not in (None, 0, 1)]
    india_macro = cfg.get("india_desk", {}).get("macro", {})
    result = {
        "status": status,
        "ok_count": ok_count,
        "total": total,
        "probes": probes,
        "feeds": feeds,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "notes": [],
    }
    if stale_yahoo:
        result["notes"].append(
            f"{len(stale_yahoo)} Yahoo probe(s) have bars older than 1 day — weekend/holiday or feed lag."
        )
    if india_macro.get("repo_rate") is not None:
        result["notes"].append(
            f"India repo rate {india_macro.get('repo_rate')}% from config — verify vs RBI when publishing"
        )
    result["notes"].append(
        "Free-tier ceiling: Yahoo + CoinGecko + AMFI. Vendor feeds (Bloomberg, NSE paid) would improve reliability."
    )
    if ttl > 0:
        cache_set_json(key, result, ttl)
    return result
