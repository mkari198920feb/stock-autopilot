from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from stock_autopilot.config import settings
from stock_autopilot.models.schemas import (
    AgentRunResult,
    CryptoPulseSnapshot,
    GlobalDeskSnapshot,
    IndiaDeskSnapshot,
    MacroSnapshot,
    MarketPulseSnapshot,
    ModelPortfolio,
    StockPick,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                scanned INTEGER,
                macro_json TEXT NOT NULL,
                log_json TEXT
            );
            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            CREATE INDEX IF NOT EXISTS idx_picks_run ON picks(run_id);
            CREATE TABLE IF NOT EXISTS model_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            CREATE INDEX IF NOT EXISTS idx_models_run ON model_portfolios(run_id);
            CREATE TABLE IF NOT EXISTS crypto_pulse (
                pulse_id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_crypto_pulse_time ON crypto_pulse(captured_at);
            CREATE TABLE IF NOT EXISTS india_desk (
                desk_id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_india_desk_time ON india_desk(captured_at);
            CREATE TABLE IF NOT EXISTS global_desk (
                desk_id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_global_desk_time ON global_desk(captured_at);
            CREATE TABLE IF NOT EXISTS market_pulse (
                pulse_id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_market_pulse_time ON market_pulse(captured_at);
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at);
            CREATE TABLE IF NOT EXISTS pick_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                desk_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                captured_at TEXT NOT NULL,
                entry_price REAL NOT NULL,
                target_price REAL,
                upside_pct REAL,
                rating TEXT,
                bias TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_pick_snap_time ON pick_snapshots(captured_at);
            CREATE TABLE IF NOT EXISTS pick_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                due_at TEXT NOT NULL,
                resolved_at TEXT,
                entry_price REAL NOT NULL,
                exit_price REAL,
                return_pct REAL,
                target_hit INTEGER,
                outcome TEXT,
                rating TEXT,
                bias TEXT,
                upside_pct REAL,
                FOREIGN KEY (snapshot_id) REFERENCES pick_snapshots(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pick_outcomes_due ON pick_outcomes(due_at, resolved_at);
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _normalize_pick(payload: dict) -> dict:
    """Patch legacy/null research note fields so dashboard never 500s."""
    note = payload.get("research_note")
    if not note:
        return payload
    support = note.get("support") or 0
    resistance = note.get("resistance") or 0
    spot = note.get("current_price") or support or resistance
    if spot and not note.get("current_price"):
        note["current_price"] = spot
    if spot and not note.get("price_target"):
        note["price_target"] = round(float(spot) * 1.12, 2)
    if note.get("upside_pct") is None and spot:
        pt = note.get("price_target") or spot
        note["upside_pct"] = round((float(pt) / float(spot) - 1) * 100, 1)
    if note.get("downside_pct") is None and spot:
        note["downside_pct"] = 12.0
    if note.get("rsi") is None:
        note["rsi"] = 50.0
    payload["research_note"] = note
    return payload


def save_run(result: AgentRunResult) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (run_id, started_at, finished_at, status, scanned, macro_json, log_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                result.started_at.isoformat(),
                result.finished_at.isoformat(),
                result.status,
                result.scanned,
                result.macro.model_dump_json(),
                json.dumps(result.log),
            ),
        )
        conn.execute("DELETE FROM picks WHERE run_id = ?", (result.run_id,))
        for i, pick in enumerate(result.picks, start=1):
            conn.execute(
                "INSERT INTO picks (run_id, rank, symbol, payload_json) VALUES (?, ?, ?, ?)",
                (result.run_id, i, pick.symbol, pick.model_dump_json()),
            )
        conn.execute("DELETE FROM model_portfolios WHERE run_id = ?", (result.run_id,))
        for model in result.model_portfolios:
            conn.execute(
                "INSERT INTO model_portfolios (run_id, model_id, payload_json) VALUES (?, ?, ?)",
                (result.run_id, model.model_id, model.model_dump_json()),
            )


def get_latest_run() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM runs ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        picks = conn.execute(
            "SELECT payload_json FROM picks WHERE run_id = ? ORDER BY rank",
            (row["run_id"],),
        ).fetchall()
        models = conn.execute(
            "SELECT payload_json FROM model_portfolios WHERE run_id = ? ORDER BY model_id",
            (row["run_id"],),
        ).fetchall()
        return {
            "run_id": row["run_id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "scanned": row["scanned"],
            "macro": json.loads(row["macro_json"]),
            "log": json.loads(row["log_json"] or "[]"),
            "picks": [_normalize_pick(json.loads(p["payload_json"])) for p in picks],
            "model_portfolios": [json.loads(m["payload_json"]) for m in models],
        }


def list_runs(limit: int = 14) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, finished_at, status, scanned FROM runs ORDER BY finished_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_crypto_pulse(pulse: CryptoPulseSnapshot) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO crypto_pulse (pulse_id, captured_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (pulse.pulse_id, pulse.captured_at.isoformat(), pulse.model_dump_json()),
        )


def get_latest_crypto_pulse() -> CryptoPulseSnapshot | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM crypto_pulse ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return CryptoPulseSnapshot(**json.loads(row["payload_json"]))


def get_latest_crypto_pulse_dict() -> dict | None:
    pulse = get_latest_crypto_pulse()
    if not pulse:
        return None
    return pulse.model_dump(mode="json")


def save_india_desk(snapshot: IndiaDeskSnapshot) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO india_desk (desk_id, captured_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (snapshot.desk_id, snapshot.captured_at.isoformat(), snapshot.model_dump_json()),
        )


def get_latest_india_desk() -> IndiaDeskSnapshot | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM india_desk ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return IndiaDeskSnapshot(**json.loads(row["payload_json"]))


def get_latest_india_desk_dict() -> dict | None:
    snap = get_latest_india_desk()
    return snap.model_dump(mode="json") if snap else None


def save_global_desk(snapshot: GlobalDeskSnapshot) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO global_desk (desk_id, captured_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (snapshot.desk_id, snapshot.captured_at.isoformat(), snapshot.model_dump_json()),
        )


def get_latest_global_desk() -> GlobalDeskSnapshot | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM global_desk ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return GlobalDeskSnapshot(**json.loads(row["payload_json"]))


def get_latest_global_desk_dict() -> dict | None:
    snap = get_latest_global_desk()
    return snap.model_dump(mode="json") if snap else None


def save_market_pulse(snapshot: MarketPulseSnapshot) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO market_pulse (pulse_id, captured_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (snapshot.pulse_id, snapshot.captured_at.isoformat(), snapshot.model_dump_json()),
        )


def get_latest_market_pulse() -> MarketPulseSnapshot | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM market_pulse ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MarketPulseSnapshot(**json.loads(row["payload_json"]))


def get_latest_market_pulse_dict() -> dict | None:
    snap = get_latest_market_pulse()
    return snap.model_dump(mode="json") if snap else None


# --- API cache ---

def cache_get_raw(key: str) -> str | None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM api_cache WHERE cache_key = ? AND expires_at > ?",
            (key, now),
        ).fetchone()
        return row["payload_json"] if row else None


def cache_set_raw(key: str, payload: str, ttl_seconds: int) -> None:
    expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO api_cache (cache_key, payload_json, expires_at)
            VALUES (?, ?, ?)
            """,
            (key, payload, expires),
        )


def cache_delete_expired() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM api_cache WHERE expires_at <= ?", (now,))


# --- Pick outcome tracking ---

_OUTCOME_HORIZONS = {"1d": 1, "7d": 7, "30d": 30}


def insert_pick_snapshots(rows: list[dict]) -> None:
    if not rows:
        return
    with get_conn() as conn:
        for row in rows:
            captured = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            cur = conn.execute(
                """
                INSERT INTO pick_snapshots
                (source, desk_id, symbol, name, captured_at, entry_price, target_price, upside_pct, rating, bias)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["source"],
                    row["desk_id"],
                    row["symbol"],
                    row.get("name"),
                    row["captured_at"],
                    row["entry_price"],
                    row.get("target_price"),
                    row.get("upside_pct"),
                    row.get("rating"),
                    row.get("bias"),
                ),
            )
            snap_id = cur.lastrowid
            for horizon, days in _OUTCOME_HORIZONS.items():
                due = (captured + timedelta(days=days)).isoformat()
                conn.execute(
                    """
                    INSERT INTO pick_outcomes
                    (snapshot_id, source, symbol, horizon, due_at, entry_price, rating, bias, upside_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap_id,
                        row["source"],
                        row["symbol"],
                        horizon,
                        due,
                        row["entry_price"],
                        row.get("rating"),
                        row.get("bias"),
                        row.get("upside_pct"),
                    ),
                )


def get_pending_outcomes() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, source, symbol, horizon, due_at, entry_price, rating, bias, upside_pct
            FROM pick_outcomes
            WHERE resolved_at IS NULL AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT 200
            """,
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_outcome_row(
    outcome_id: int,
    exit_price: float,
    return_pct: float,
    outcome: str,
    target_hit: bool | None,
    resolved_at: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE pick_outcomes
            SET exit_price = ?, return_pct = ?, outcome = ?, target_hit = ?, resolved_at = ?
            WHERE id = ?
            """,
            (
                exit_price,
                return_pct,
                outcome,
                1 if target_hit else (0 if target_hit is False else None),
                resolved_at,
                outcome_id,
            ),
        )


def get_outcome_stats() -> dict:
    from stock_autopilot.db import get_conn
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with get_conn() as conn:
        open_calls = conn.execute(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT symbol, source FROM pick_snapshots
                WHERE captured_at >= ?
                GROUP BY symbol, source
            )
            """,
            (cutoff,),
        ).fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) AS c FROM pick_outcomes WHERE resolved_at IS NOT NULL").fetchone()["c"]
        hits = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_outcomes WHERE resolved_at IS NOT NULL AND outcome = 'HIT'"
        ).fetchone()["c"]
        misses = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_outcomes WHERE resolved_at IS NOT NULL AND outcome = 'MISS'"
        ).fetchone()["c"]
        partial = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_outcomes WHERE resolved_at IS NOT NULL AND outcome = 'PARTIAL'"
        ).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_outcomes WHERE resolved_at IS NULL"
        ).fetchone()["c"]

        def _horizon_stats(h: str) -> dict:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS n,
                    SUM(CASE WHEN outcome = 'HIT' THEN 1 ELSE 0 END) AS hits,
                    AVG(return_pct) AS avg_ret
                FROM pick_outcomes
                WHERE resolved_at IS NOT NULL AND horizon = ?
                """,
                (h,),
            ).fetchone()
            n = row["n"] or 0
            hhits = row["hits"] or 0
            return {
                "resolved": n,
                "hit_rate_pct": round(hhits / n * 100, 1) if n else None,
                "avg_return_pct": round(row["avg_ret"], 2) if row["avg_ret"] is not None else None,
            }

        recent = conn.execute(
            """
            SELECT symbol, source, horizon, outcome, return_pct, resolved_at, rating
            FROM pick_outcomes
            WHERE resolved_at IS NOT NULL
            ORDER BY resolved_at DESC
            LIMIT 8
            """
        ).fetchall()

        hit_rate = round(hits / total * 100, 1) if total else None
        return {
            "total_resolved": total,
            "hits": hits,
            "misses": misses,
            "partial": partial,
            "pending": pending,
            "open_calls_logged": open_calls,
            "hit_rate_pct": hit_rate,
            "horizon_7d": _horizon_stats("7d"),
            "horizon_30d": _horizon_stats("30d"),
            "recent": [dict(r) for r in recent],
            "has_data": total > 0,
        }


def get_app_setting(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_app_setting(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, value, now),
        )
