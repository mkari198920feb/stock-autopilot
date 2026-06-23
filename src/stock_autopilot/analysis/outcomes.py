from __future__ import annotations

from datetime import datetime, timezone, timedelta

from stock_autopilot.collectors.quotes import batch_fetch_quotes
from stock_autopilot.db import (
    get_outcome_stats,
    get_pending_outcomes,
    insert_pick_snapshots,
    resolve_outcome_row,
)
from stock_autopilot.models.schemas import CryptoPulseSnapshot, CommoditiesDeskSnapshot, IndiaDeskSnapshot, StockPick


HORIZONS_DAYS = {"1d": 1, "7d": 7, "30d": 30}
_LIVE_CACHE_KEY = "track_record:live_open"
_LIVE_CACHE_TTL = 180
_CRYPTO_QUOTE = {"BTC": "BTC-USD", "ETH": "ETH-USD"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_age(captured_at: str) -> str:
    try:
        ts = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        mins = int((_now() - ts).total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 48:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ""


def _classify_equity(
    entry: float,
    exit_p: float,
    upside_pct: float | None,
    rating: str | None,
    horizon: str,
) -> tuple[float, str, bool | None]:
    ret = (exit_p / entry - 1) * 100 if entry > 0 else 0.0
    target_hit = None
    if upside_pct and upside_pct > 0:
        target_hit = ret >= upside_pct * (0.5 if horizon == "7d" else 0.85)

    rating_u = (rating or "").upper()
    if "SELL" in rating_u or "REDUCE" in rating_u:
        outcome = "HIT" if ret < 0 else "MISS" if ret > 3 else "PARTIAL"
    elif "BUY" in rating_u or "ACCUM" in rating_u:
        if ret >= 3:
            outcome = "HIT"
        elif ret <= -5:
            outcome = "MISS"
        else:
            outcome = "PARTIAL"
    else:
        outcome = "NEUTRAL" if abs(ret) < 2 else ("HIT" if ret > 0 else "MISS")
    return round(ret, 3), outcome, target_hit


def _classify_crypto_bias(entry: float, exit_p: float, bias: str | None) -> tuple[float, str, bool | None]:
    ret = (exit_p / entry - 1) * 100 if entry > 0 else 0.0
    b = (bias or "neutral").lower()
    if b == "bullish":
        outcome = "HIT" if ret > 0.5 else "MISS" if ret < -0.5 else "PARTIAL"
    elif b == "bearish":
        outcome = "HIT" if ret < -0.5 else "MISS" if ret > 0.5 else "PARTIAL"
    else:
        outcome = "NEUTRAL" if abs(ret) < 1 else ("HIT" if ret > 0 else "MISS")
    return round(ret, 3), outcome, None


def record_autopilot_picks(run_id: str, captured_at: datetime, picks: list[StockPick]) -> None:
    rows = []
    for p in picks:
        note = p.research_note
        entry = note.current_price if note and note.current_price else None
        if not entry:
            continue
        rows.append(
            {
                "source": "autopilot",
                "desk_id": run_id,
                "symbol": p.symbol,
                "name": p.name,
                "captured_at": captured_at.isoformat(),
                "entry_price": entry,
                "target_price": note.price_target if note else None,
                "upside_pct": note.upside_pct if note else None,
                "rating": note.rating if note else None,
                "bias": None,
            }
        )
    insert_pick_snapshots(rows)


def record_global_desk_picks(desk_id: str, captured_at: datetime, picks: list) -> None:
    rows = []
    for p in picks:
        d = p.model_dump() if hasattr(p, "model_dump") else p
        rows.append(
            {
                "source": "global_desk",
                "desk_id": desk_id,
                "symbol": d["symbol"],
                "name": d.get("name", d["symbol"]),
                "captured_at": captured_at.isoformat(),
                "entry_price": d["cmp"],
                "target_price": d.get("target"),
                "upside_pct": d.get("upside_pct"),
                "rating": d.get("rating"),
                "bias": None,
            }
        )
    insert_pick_snapshots(rows)


def record_india_picks(snapshot: IndiaDeskSnapshot) -> None:
    rows = []
    for eq in snapshot.equities:
        rows.append(
            {
                "source": "india_desk",
                "desk_id": snapshot.desk_id,
                "symbol": eq.symbol,
                "name": eq.name,
                "captured_at": snapshot.captured_at.isoformat(),
                "entry_price": eq.cmp,
                "target_price": eq.target_12m,
                "upside_pct": eq.upside_pct,
                "rating": eq.rating,
                "bias": None,
            }
        )
    insert_pick_snapshots(rows)


def record_crypto_pulse(pulse: CryptoPulseSnapshot) -> None:
    rows = []
    for coin in (pulse.btc, pulse.eth):
        rows.append(
            {
                "source": "crypto_pulse",
                "desk_id": pulse.pulse_id,
                "symbol": coin.asset,
                "name": coin.asset,
                "captured_at": pulse.captured_at.isoformat(),
                "entry_price": coin.current_price,
                "target_price": coin.target_upside,
                "upside_pct": coin.target_upside_pct,
                "rating": coin.bias_label,
                "bias": coin.bias_class,
            }
        )
    insert_pick_snapshots(rows)


def record_commodities_desk(snapshot: CommoditiesDeskSnapshot) -> None:
    rows = []
    for pick in snapshot.desk_picks:
        rows.append(
            {
                "source": "commodities_desk",
                "desk_id": snapshot.desk_id,
                "symbol": pick.symbol,
                "name": pick.name,
                "captured_at": snapshot.captured_at.isoformat(),
                "entry_price": pick.price,
                "target_price": None,
                "upside_pct": pick.change_1m_pct,
                "rating": pick.bias_label,
                "bias": pick.bias_class,
            }
        )
    insert_pick_snapshots(rows)


def _quote_symbol(symbol: str, source: str) -> str:
    if source == "crypto_pulse":
        return _CRYPTO_QUOTE.get(symbol.upper(), f"{symbol.upper()}-USD")
    return symbol


def resolve_due_outcomes() -> int:
    from stock_autopilot.collectors.quotes import fetch_quote

    pending = get_pending_outcomes()
    resolved = 0
    now = _now()
    for row in pending:
        due = datetime.fromisoformat(row["due_at"].replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due > now:
            continue

        symbol = _quote_symbol(row["symbol"], row["source"])
        exit_p = fetch_quote(symbol)
        if exit_p is None:
            continue

        entry = float(row["entry_price"])
        horizon = row["horizon"]
        if row["source"] == "crypto_pulse":
            ret, outcome, target_hit = _classify_crypto_bias(entry, exit_p, row.get("bias"))
        elif row["source"] == "commodities_desk":
            ret, outcome, target_hit = _classify_crypto_bias(entry, exit_p, row.get("bias"))
        else:
            ret, outcome, target_hit = _classify_equity(
                entry, exit_p, row.get("upside_pct"), row.get("rating"), horizon
            )

        resolve_outcome_row(row["id"], exit_p, ret, outcome, target_hit, now.isoformat())
        resolved += 1
    return resolved


def get_live_open_performance(force_refresh: bool = False) -> dict:
    """Unrealized return on latest snapshots using batched live quotes."""
    from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
    from stock_autopilot.db import get_conn

    if not force_refresh:
        hit = cache_get_json(_LIVE_CACHE_KEY)
        if isinstance(hit, dict) and hit.get("items") is not None:
            return hit

    cutoff = (_now() - timedelta(days=30)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, source, entry_price, captured_at, rating, target_price, upside_pct
            FROM pick_snapshots
            WHERE captured_at >= ?
            ORDER BY captured_at DESC
            """,
            (cutoff,),
        ).fetchall()

    if not rows:
        empty = {"count": 0, "avg_return_pct": None, "win_rate_pct": None, "items": [], "updated_at": _now().isoformat()}
        cache_set_json(_LIVE_CACHE_KEY, empty, _LIVE_CACHE_TTL)
        return empty

    seen: set[tuple[str, str]] = set()
    pending_rows: list = []
    for row in rows:
        key = (row["symbol"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        if float(row["entry_price"]) <= 0:
            continue
        pending_rows.append(row)
        if len(pending_rows) >= 12:
            break

    symbols = [_quote_symbol(r["symbol"], r["source"]) for r in pending_rows]
    quotes = batch_fetch_quotes(symbols, ttl=90)

    items: list[dict] = []
    returns: list[float] = []
    failed: list[str] = []

    for row, quote_sym in zip(pending_rows, symbols):
        symbol = row["symbol"]
        entry = float(row["entry_price"])
        exit_p = quotes.get(quote_sym)
        if exit_p is None:
            failed.append(symbol)
            continue
        ret = round((exit_p / entry - 1) * 100, 3)
        returns.append(ret)
        items.append(
            {
                "symbol": symbol,
                "source": row["source"],
                "return_pct": ret,
                "rating": row["rating"],
                "entry_price": round(entry, 4 if entry < 10 else 2),
                "current_price": round(exit_p, 4 if exit_p < 10 else 2),
                "target_price": row["target_price"],
                "upside_pct": row["upside_pct"],
                "captured_at": row["captured_at"],
                "age_label": _format_age(row["captured_at"]),
            }
        )

    avg = round(sum(returns) / len(returns), 3) if returns else None
    winners = sum(1 for r in returns if r > 0.05)
    losers = sum(1 for r in returns if r < -0.05)
    flat = len(returns) - winners - losers

    result = {
        "count": len(items),
        "avg_return_pct": avg,
        "win_rate_pct": round(winners / len(returns) * 100, 1) if returns else None,
        "winners": winners,
        "losers": losers,
        "flat": flat,
        "items": items[:8],
        "failed_symbols": failed,
        "updated_at": _now().isoformat(),
        "stale": len(failed) > 0 and len(items) == 0,
    }
    cache_set_json(_LIVE_CACHE_KEY, result, _LIVE_CACHE_TTL)
    return result


def track_record_summary(include_live: bool = True, force_live_refresh: bool = False) -> dict:
    stats = get_outcome_stats()
    if include_live:
        stats["live_open"] = get_live_open_performance(force_refresh=force_live_refresh)
    else:
        stats["live_open"] = {"count": 0, "items": [], "loading": True}
    try:
        from stock_autopilot.analysis.signal_backtest import signal_validation_report

        stats["validation"] = signal_validation_report()
    except Exception:
        stats["validation"] = {"methodology": "rule_based", "confidence": "low", "notes": []}
    return stats
