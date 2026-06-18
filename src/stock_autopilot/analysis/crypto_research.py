from __future__ import annotations

from stock_autopilot.collectors.coingecko import fetch_coin_detail, fetch_market_batch, symbol_to_id
from stock_autopilot.universe import brand_cfg


def build_crypto_research_note(symbol: str) -> dict | None:
    token = symbol.upper().replace("-USD", "").replace("USDT", "")
    coin_id = symbol_to_id(token)
    if not coin_id:
        return None

    markets = fetch_market_batch([coin_id])
    detail = fetch_coin_detail(coin_id)
    if not markets and not detail:
        return None

    m = markets[0] if markets else {}
    d = detail or {}
    md = d.get("market_data") or {}
    price = float(m.get("current_price") or md.get("current_price", {}).get("usd") or 0)
    if price <= 0:
        return None

    chg_7d = m.get("price_change_percentage_7d_in_currency") or md.get("price_change_percentage_7d")
    chg_24h = m.get("price_change_percentage_24h_in_currency") or md.get("price_change_percentage_24h")
    mcap = m.get("market_cap") or md.get("market_cap", {}).get("usd")
    rank = m.get("market_cap_rank") or d.get("market_cap_rank")
    ath = md.get("ath", {}).get("usd")
    ath_chg = md.get("ath_change_percentage", {}).get("usd")

    tier = 1 if token in ("BTC", "ETH") else 2 if rank and rank <= 30 else 4 if rank and rank <= 100 else 6
    if token in ("DOGE", "SHIB", "PEPE", "WIF", "BONK"):
        tier = 10

    if chg_7d is not None and chg_7d > 5:
        bias, bias_class = "BULLISH", "bullish"
    elif chg_7d is not None and chg_7d < -5:
        bias, bias_class = "BEARISH", "bearish"
    else:
        bias, bias_class = "NEUTRAL", "neutral"

    dev = d.get("developer_data") or {}
    commits = (dev.get("commit_count_4_weeks") or 0) if dev else 0
    dev_activity = "High" if commits > 100 else "Medium" if commits > 20 else "Low"

    circ = md.get("circulating_supply")
    max_s = md.get("max_supply")
    circ_pct = round(float(circ) / float(max_s) * 100, 1) if circ and max_s else None

    support = price * 0.92
    resistance = price * 1.12
    bull = price * (1.25 if tier <= 3 else 1.15)
    base = price * 1.08
    bear = price * 0.85

    desk = brand_cfg()["crypto_header"]
    name = d.get("name") or m.get("name") or token

    if tier >= 10:
        bull = base = None
        desk_note = "Momentum-only — no fundamental price target; max 1–2% tactical size."
    else:
        desk_note = (
            f"Market prices {token} on 7D momentum alone; "
            f"{'undervalued vs recent ATH' if ath_chg and ath_chg > -40 else 'extended vs support'} on current tape."
        )

    return {
        "header": desk,
        "token": name,
        "ticker": token,
        "category": d.get("categories", ["Crypto"])[0] if d.get("categories") else "Crypto",
        "chain": d.get("asset_platform_id") or "Native",
        "market_cap_usd": mcap,
        "rank": rank,
        "risk_tier": min(5, tier if tier <= 5 else 5),
        "bias": bias,
        "bias_class": bias_class,
        "price": round(price, 6 if price < 1 else 2),
        "momentum_7d_pct": round(chg_7d, 2) if chg_7d is not None else None,
        "momentum_24h_pct": round(chg_24h, 2) if chg_24h is not None else None,
        "use_case": (d.get("description") or "")[:280] or f"{name} on-chain asset.",
        "competitive_moat": "Network effects + liquidity depth" if rank and rank <= 20 else "Ecosystem niche",
        "token_utility": "Required for network fees/governance" if tier <= 4 else "Utility varies",
        "developer_activity": dev_activity,
        "circulating_pct": circ_pct,
        "support": round(support, 4 if price < 1 else 2),
        "resistance": round(resistance, 4 if price < 1 else 2),
        "bull_case": round(bull, 4 if bull and bull < 1 else 2) if bull else None,
        "base_case": round(base, 4 if base < 1 else 2) if tier < 10 else None,
        "bear_case": round(bear, 4 if bear < 1 else 2),
        "stop_loss": round(support * 0.97, 4 if price < 1 else 2),
        "size_balanced_pct": 0 if tier >= 10 else (5 if tier == 1 else 3 if tier <= 3 else 1),
        "size_aggressive_pct": 0 if tier >= 10 else (10 if tier == 1 else 5 if tier <= 3 else 2),
        "desk_note": desk_note,
        "ath_usd": ath,
        "ath_drawdown_pct": round(ath_chg, 1) if ath_chg is not None else None,
        "coingecko_id": coin_id,
    }
