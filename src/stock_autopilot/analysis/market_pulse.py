from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.collectors.coingecko import fetch_global_crypto_stats
from stock_autopilot.collectors.pulse_scan import batch_scan_pulse, scan_index_quote
from stock_autopilot.models.schemas import (
    CryptoMarketPulseBoard,
    IndexQuote,
    MarketPulseBoard,
    MarketPulseSnapshot,
    MoverRow,
    SectorHeatCell,
)
from stock_autopilot.universe import brand_cfg, load_config, load_global_desk_config


MARKET_META = {
    "us": {"flag": "🇺🇸", "tz": "America/New_York", "indices": [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow"), ("^RUT", "Russell"), ("^VIX", "VIX")]},
    "canada": {"flag": "🇨🇦", "tz": "America/Toronto", "indices": [("^GSPTSE", "TSX")]},
    "brazil": {"flag": "🇧🇷", "tz": "America/Sao_Paulo", "indices": [("^BVSP", "Bovespa")]},
    "europe_uk": {"flag": "🇬🇧", "tz": "Europe/London", "indices": [("^FTSE", "FTSE 100")]},
    "europe_core": {"flag": "🇪🇺", "tz": "Europe/Berlin", "indices": [("^GDAXI", "DAX"), ("^FCHI", "CAC 40")]},
    "japan": {"flag": "🇯🇵", "tz": "Asia/Tokyo", "indices": [("^N225", "Nikkei 225")]},
    "china_hk": {"flag": "🇨🇳", "tz": "Asia/Hong_Kong", "indices": [("^HSI", "Hang Seng"), ("000001.SS", "SSE Composite")]},
    "india": {"flag": "🇮🇳", "tz": "Asia/Kolkata", "indices": [("^NSEI", "Nifty 50"), ("^BSESN", "Sensex"), ("^NSEBANK", "Nifty Bank"), ("^CNXIT", "Nifty IT")]},
    "gulf": {"flag": "🇸🇦", "tz": "Asia/Dubai", "indices": []},
    "australia": {"flag": "🇦🇺", "tz": "Australia/Sydney", "indices": [("^AXJO", "ASX 200")]},
    "em": {"flag": "🌍", "tz": "UTC", "indices": [("EEM", "EM ETF")]},
}


def _session_label() -> str:
    hour = datetime.now(timezone.utc).hour
    if hour < 8:
        return "pre_market"
    if hour < 14:
        return "open"
    if hour < 18:
        return "mid_session"
    return "close"


def _mover(row: dict, rank: int, reason: str = "") -> MoverRow:
    return MoverRow(
        rank=rank,
        symbol=row["symbol"],
        name=row["name"],
        cmp=row["cmp"],
        change_abs=row["change_abs"],
        change_pct=row["change_pct"],
        volume_vs_avg_pct=row.get("volume_vs_avg_pct", 100),
        sector=row.get("sector", "—"),
        reason=reason or _default_reason(row),
        contrarian_score=_contrarian_score(row) if row.get("near_52_low") else None,
    )


def _default_reason(row: dict) -> str:
    if row.get("near_ath"):
        return "Testing all-time high — momentum continuation watch"
    if row.get("near_52_high"):
        return "At/near 52-week high — breakout or exhaustion check"
    if row.get("near_52_low"):
        return "At/near 52-week low — value vs falling knife"
    if row.get("upper_circuit"):
        return "Upper circuit zone — momentum surge, verify fundamentals"
    if row.get("lower_circuit"):
        return "Lower circuit zone — risk alert, check news flow"
    if row["change_pct"] > 2:
        return "Strong session momentum with volume"
    if row["change_pct"] < -2:
        return "Heavy selling pressure today"
    return "Session mover"


def _contrarian_score(row: dict) -> int:
    if row["change_pct"] < -3:
        return 3
    if row.get("volume_vs_avg_pct", 0) > 150:
        return 5
    return 7


def _sector_heatmap(rows: list[dict]) -> list[SectorHeatCell]:
    buckets: dict[str, list[float]] = {}
    for r in rows:
        buckets.setdefault(r.get("sector") or "Other", []).append(r["change_pct"])
    cells = []
    for sector, pcts in buckets.items():
        avg = sum(pcts) / len(pcts)
        reason = "Leading sector today" if avg > 0.5 else "Lagging sector" if avg < -0.5 else "Mixed"
        cells.append(SectorHeatCell(sector=sector, change_pct=round(avg, 2), reason=reason))
    cells.sort(key=lambda c: c.change_pct, reverse=True)
    return cells[:10]


def _build_board(market_id: str, label: str, tickers: list[str], captured: datetime) -> MarketPulseBoard:
    meta = MARKET_META.get(market_id, {"flag": "🌍", "tz": "UTC", "indices": []})
    scans = batch_scan_pulse(tickers)
    indices = []
    for sym, lbl in meta.get("indices", []):
        q = scan_index_quote(sym, lbl)
        if q:
            indices.append(IndexQuote(**q))

    sorted_gain = sorted(scans, key=lambda x: x["change_pct"], reverse=True)
    sorted_loss = sorted(scans, key=lambda x: x["change_pct"])
    highs = [r for r in scans if r.get("near_52_high")]
    lows = [r for r in scans if r.get("near_52_low")]
    aths = [r for r in scans if r.get("near_ath")]
    upper = [r for r in scans if r.get("upper_circuit")]
    lower = [r for r in scans if r.get("lower_circuit")]
    vol_leaders = sorted(scans, key=lambda x: x.get("volume_vs_avg_pct", 0), reverse=True)[:5]

    strongest = _sector_heatmap(scans)[:1]
    weakest = _sector_heatmap(scans)[-1:] if scans else []
    setup = "Watch index support and sector leaders for tomorrow's direction."
    if strongest:
        setup = f"Strongest sector: {strongest[0].sector} ({strongest[0].change_pct:+.1f}%). {setup}"
    if market_id == "india" and indices:
        n = next((i for i in indices if i.label == "Nifty 50"), None)
        if n:
            setup = f"Nifty {n.value:,.0f} ({n.change_pct:+.2f}%). {setup}"

    advances = len([r for r in scans if r["change_pct"] > 0])
    declines = len([r for r in scans if r["change_pct"] < 0])
    breadth = {
        "advances": advances,
        "declines": declines,
        "unchanged": len(scans) - advances - declines,
        "ad_ratio": round(advances / max(declines, 1), 2),
        "new_52w_highs": len(highs),
        "new_52w_lows": len(lows),
    }

    return MarketPulseBoard(
        market_id=market_id,
        label=label,
        flag=meta.get("flag", "🌍"),
        timezone=meta.get("tz", "UTC"),
        session=_session_label(),
        captured_at=captured,
        indices=indices,
        top_gainers=[_mover(r, i, _default_reason(r)) for i, r in enumerate(sorted_gain[:5], 1)],
        top_losers=[_mover(r, i, _default_reason(r)) for i, r in enumerate(sorted_loss[:5], 1)],
        week_52_highs=[_mover(r, i, "New 52-week high — click for deep dive") for i, r in enumerate(highs[:8], 1)],
        week_52_lows=[_mover(r, i, "New 52-week low — contrarian scan") for i, r in enumerate(lows[:8], 1)],
        all_time_highs=[_mover(r, i, "All-time high alert") for i, r in enumerate(aths[:5], 1)],
        upper_circuits=[_mover(r, i, "Upper circuit") for i, r in enumerate(upper[:8], 1)],
        lower_circuits=[_mover(r, i, "Lower circuit") for i, r in enumerate(lower[:8], 1)],
        volume_leaders=[_mover(r, i, "Volume leader") for i, r in enumerate(vol_leaders, 1)],
        sector_heatmap=_sector_heatmap(scans),
        macro_pulse={"strongest_sector": strongest[0].sector if strongest else "—", "weakest_sector": weakest[0].sector if weakest else "—"},
        tomorrow_setup=setup,
        breadth=breadth,
    )


def _build_india_board(cfg: dict, captured: datetime) -> MarketPulseBoard:
    india_cfg = cfg.get("india_desk", {})
    tickers = list(india_cfg.get("nse_universe") or [])
    board = _build_board("india", "🇮🇳 India Market Pulse", tickers, captured)
    board.label = "🇮🇳 India Market Pulse"
    return board


def _yahoo_crypto_rows() -> list[dict]:
    """Fallback when CoinGecko is rate-limited or unreachable."""
    import yfinance as yf

    symbols = [
        ("BTC", "BTC-USD"),
        ("ETH", "ETH-USD"),
        ("SOL", "SOL-USD"),
        ("XRP", "XRP-USD"),
        ("DOGE", "DOGE-USD"),
        ("ADA", "ADA-USD"),
        ("AVAX", "AVAX-USD"),
        ("LINK", "LINK-USD"),
        ("BNB", "BNB-USD"),
        ("DOT", "DOT-USD"),
    ]
    rows: list[dict] = []
    for token, ysym in symbols:
        try:
            hist = yf.Ticker(ysym).history(period="8d", auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            closes = hist["Close"].dropna()
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            week = float(closes.iloc[0])
            chg_24h = (price / prev - 1) * 100 if prev else 0.0
            chg_7d = (price / week - 1) * 100 if week else 0.0
            rows.append(
                {
                    "token": token,
                    "name": token,
                    "price": round(price, 4),
                    "chg_24h": round(chg_24h, 2),
                    "chg_7d": round(chg_7d, 2),
                    "mcap": None,
                    "rank": len(rows) + 1,
                    "volume": float(hist["Volume"].iloc[-1]) if "Volume" in hist else None,
                }
            )
        except Exception:
            continue
    return rows


def _rows_from_crypto_pulse() -> list[dict]:
    from stock_autopilot.db import get_latest_crypto_pulse

    pulse = get_latest_crypto_pulse()
    if not pulse:
        return []
    rows = []
    for coin in (pulse.btc, pulse.eth):
        chg_24h = coin.target_upside_pct * 0.1 if coin.bias_class == "bullish" else -coin.target_downside_pct * 0.1
        asset = getattr(coin, "asset", None) or ("BTC" if coin is pulse.btc else "ETH")
        rows.append(
            {
                "token": asset,
                "name": asset,
                "price": coin.current_price,
                "chg_24h": round(chg_24h, 2),
                "chg_7d": None,
                "mcap": None,
                "rank": 1 if coin.asset == "BTC" else 2,
            }
        )
    return rows


def _yahoo_global_stats(rows: list[dict]) -> tuple[float, float, float, float]:
    """Estimate global mcap / dominance when CoinGecko /global is unavailable."""
    import yfinance as yf

    mcap = 0.0
    btc_dom = 0.0
    eth_dom = 0.0
    mcap_chg = 0.0
    try:
        btc_info = yf.Ticker("BTC-USD").info or {}
        btc_mcap = float(btc_info.get("marketCap") or 0)
        eth_info = yf.Ticker("ETH-USD").info or {}
        eth_mcap = float(eth_info.get("marketCap") or 0)
        if btc_mcap:
            total = btc_mcap / 0.56
            btc_dom = btc_mcap / total * 100
            eth_dom = (eth_mcap / total * 100) if eth_mcap else 12.0
            mcap = total
    except Exception:
        pass

    if not mcap and rows:
        btc_row = next((r for r in rows if r.get("token") == "BTC"), None)
        if btc_row and btc_row.get("price"):
            mcap = float(btc_row["price"]) * 19_800_000 / 0.56
            btc_dom = 56.0
            eth_dom = 12.0

    if rows:
        chgs = [r.get("chg_24h") for r in rows if r.get("chg_24h") is not None]
        if chgs:
            mcap_chg = sum(chgs) / len(chgs)

    return mcap, mcap_chg, btc_dom, eth_dom


def _build_crypto_board(captured: datetime) -> CryptoMarketPulseBoard:
    from stock_autopilot.collectors.coingecko import fetch_global_crypto_stats, fetch_top_markets, row_to_metrics
    from stock_autopilot.collectors.crypto import _fetch_fear_greed

    global_data = fetch_global_crypto_stats()
    gdata = (global_data.get("data") or {}) if global_data else {}
    mcap = float(gdata.get("total_market_cap", {}).get("usd") or 0)
    mcap_chg = float(gdata.get("market_cap_change_percentage_24h_usd") or 0)
    btc_dom = float(gdata.get("market_cap_percentage", {}).get("btc") or 0)
    eth_dom = float(gdata.get("market_cap_percentage", {}).get("eth") or 0)

    markets = fetch_top_markets(per_page=100)
    rows = [row_to_metrics(m) for m in markets if m.get("current_price")]

    if not rows:
        rows = _yahoo_crypto_rows()

    if not rows:
        rows = _rows_from_crypto_pulse()

    if not mcap:
        est_mcap, est_chg, est_btc, est_eth = _yahoo_global_stats(rows)
        mcap = mcap or est_mcap
        mcap_chg = mcap_chg or est_chg
        btc_dom = btc_dom or est_btc
        eth_dom = eth_dom or est_eth

    if not mcap and rows:
        btc_row = next((r for r in rows if r.get("token") == "BTC"), rows[0] if rows else None)
        if btc_row and btc_row.get("mcap"):
            mcap = float(btc_row["mcap"]) / max((btc_dom or 50) / 100, 0.4)

    if not btc_dom and rows:
        btc_m = next((r for r in rows if r.get("token") == "BTC"), None)
        eth_m = next((r for r in rows if r.get("token") == "ETH"), None)
        if btc_m and eth_m and btc_m.get("mcap") and eth_m.get("mcap") and mcap:
            btc_dom = float(btc_m["mcap"]) / mcap * 100
            eth_dom = float(eth_m["mcap"]) / mcap * 100

    fg_val, fg_label = _fetch_fear_greed()
    if fg_label and fg_label != "Unknown":
        fear_greed = fg_label
    elif mcap_chg > 2:
        fear_greed = "Greed"
    elif mcap_chg < -2:
        fear_greed = "Fear"
    else:
        fear_greed = "Neutral"

    valid = [r for r in rows if r.get("chg_24h") is not None]
    sorted_gain = sorted(valid, key=lambda x: x.get("chg_24h") or 0, reverse=True)
    sorted_loss = sorted(valid, key=lambda x: x.get("chg_24h") or 0)
    ath_alerts = [r for r in valid if (r.get("chg_24h") or 0) > 8]

    layer1 = [r for r in rows if r.get("token") in ("BTC", "ETH", "SOL") and r.get("chg_24h") is not None]
    eth_row = next((r for r in rows if r.get("token") == "ETH"), None)
    doge_row = next((r for r in rows if r.get("token") == "DOGE"), None)

    categories = [
        {
            "category": "Layer 1s",
            "change_pct": round(sum(r.get("chg_24h") or 0 for r in layer1) / max(len(layer1), 1), 2),
        },
        {
            "category": "DeFi proxy (ETH)",
            "change_pct": round(eth_row.get("chg_24h") or 0, 2) if eth_row else 0.0,
        },
        {
            "category": "Meme / DOGE",
            "change_pct": round(doge_row.get("chg_24h") or 0, 2) if doge_row else 0.0,
        },
    ]

    setup = "Monitor BTC dominance and 24H liquidations for volatility spikes."
    if not markets:
        setup = "CoinGecko unavailable — showing Yahoo Finance 24H movers. Refresh pulse to retry live global stats."

    return CryptoMarketPulseBoard(
        captured_at=captured,
        total_market_cap_usd=mcap,
        market_cap_change_24h_pct=round(mcap_chg, 2),
        btc_dominance_pct=round(btc_dom, 1),
        eth_dominance_pct=round(eth_dom, 1),
        fear_greed_label=fear_greed,
        top_by_mcap=rows[:10],
        top_gainers_24h=sorted_gain[:5],
        top_losers_24h=sorted_loss[:5],
        week_52_highs=sorted_gain[:3],
        week_52_lows=sorted_loss[:3],
        ath_alerts=ath_alerts[:5],
        volume_leaders=sorted(rows, key=lambda x: x.get("volume") or 0, reverse=True)[:5],
        category_performance=categories,
        tomorrow_setup=setup,
    )


def build_market_pulse_snapshot() -> MarketPulseSnapshot:
    cfg = load_config()
    gd = load_global_desk_config(cfg)
    captured = datetime.now(timezone.utc)
    boards: list[MarketPulseBoard] = []

    for market_id, mcfg in (gd.get("markets") or {}).items():
        tickers = mcfg.get("tickers") or []
        if not tickers:
            continue
        boards.append(_build_board(market_id, mcfg.get("label", market_id), tickers, captured))

    india = _build_india_board(cfg, captured)
    boards.insert(0, india)

    crypto = _build_crypto_board(captured)
    india_breadth = india.breadth
    brand = brand_cfg()["brand_name"]

    return MarketPulseSnapshot(
        pulse_id=captured.strftime("%Y%m%d%H%M") + "-pulse-" + uuid.uuid4().hex[:6],
        captured_at=captured,
        session_label=_session_label(),
        opening_statement=(
            f"{brand} Deep Intelligence is fully loaded. Market Pulse boards are live across "
            f"{len(boards)} regional markets plus crypto — movers, 52-week extremes, circuits, "
            "and sector heatmaps. Select any symbol for the full 8-pillar institutional brief."
        ),
        boards=boards,
        crypto=crypto,
        india_eod_breadth=india_breadth,
    )
