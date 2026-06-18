from __future__ import annotations

from stock_autopilot.collectors.coingecko import fetch_market_batch, metrics_for_symbol, symbol_to_id
from stock_autopilot.models.schemas import CryptoCategoryPick


def _bias(change_7d: float | None, tier: int) -> tuple[str, str, int]:
    if tier >= 10:
        return "MOMENTUM ONLY", "neutral", 35
    if change_7d is None:
        return "NEUTRAL", "neutral", 50
    if change_7d > 5:
        return "BULLISH", "bullish", min(88, 55 + int(change_7d))
    if change_7d < -5:
        return "BEARISH", "bearish", min(88, 55 + int(abs(change_7d)))
    return "NEUTRAL", "neutral", 52


def build_crypto_board(crypto_tiers: dict[str, dict]) -> list[CryptoCategoryPick]:
    board: list[CryptoCategoryPick] = []

    for cat_id, cat in crypto_tiers.items():
        tier = int(cat.get("tier", 3))
        symbols = cat.get("symbols") or []
        best: tuple[float, dict, dict] | None = None

        coin_ids: list[str] = []
        id_to_meta: dict[str, dict] = {}
        for entry in symbols:
            if isinstance(entry, dict):
                ticker = entry.get("ticker", "").replace("-USD", "")
                name = entry.get("name", ticker)
                cid = entry.get("coingecko_id") or symbol_to_id(ticker)
            else:
                ticker = str(entry).replace("-USD", "")
                name = ticker
                cid = symbol_to_id(ticker)
            if not cid:
                continue
            coin_ids.append(cid)
            id_to_meta[cid] = {"ticker": ticker, "name": name, "entry": entry if isinstance(entry, dict) else {}}

        market_rows = fetch_market_batch(coin_ids) if coin_ids else []
        by_id = {r.get("id"): r for r in market_rows if r.get("id")}

        for cid, meta in id_to_meta.items():
            row = by_id.get(cid)
            if row:
                m = {
                    "price": float(row.get("current_price") or 0),
                    "chg_7d": row.get("price_change_percentage_7d_in_currency"),
                    "chg_24h": row.get("price_change_percentage_24h_in_currency"),
                    "market_cap": row.get("market_cap"),
                    "rank": row.get("market_cap_rank"),
                }
            else:
                m = metrics_for_symbol(meta["ticker"], meta.get("entry"))
            if not m or not m.get("price"):
                continue
            chg_7d = m.get("chg_7d")
            score = chg_7d if chg_7d is not None else 0.0
            if tier >= 10:
                score = abs(score) if score else abs(m.get("chg_24h") or 0)
            if best is None or score > best[0]:
                best = (score, m, meta)

        if not best:
            continue

        _, metrics, meta = best
        chg_7 = metrics.get("chg_7d")
        bias, bias_class, conf = _bias(chg_7, tier)
        timeframe = "1–4H" if tier == 1 else "1–7D" if tier <= 3 else "Hours" if tier >= 10 else "1–4W"

        note = (
            f"Tier {tier} — {meta['name']}. "
            + (
                "No price target — momentum-only sizing max 1–2%."
                if tier >= 10
                else (
                    f"7D {chg_7:+.1f}% via CoinGecko · rank #{metrics.get('rank') or '—'}."
                    if chg_7 is not None
                    else "CoinGecko market data."
                )
            )
        )

        board.append(
            CryptoCategoryPick(
                category=cat.get("label", cat_id),
                tier=tier,
                token=meta["ticker"],
                name=meta["name"],
                bias=bias,
                bias_class=bias_class,
                timeframe=timeframe,
                confidence_pct=conf,
                price=round(metrics["price"], 4),
                desk_note=note,
                momentum_7d_pct=round(chg_7, 2) if chg_7 is not None else None,
            )
        )

    return sorted(board, key=lambda c: c.tier)


def crypto_market_pulse(board: list[CryptoCategoryPick]) -> dict:
    from stock_autopilot.collectors.coingecko import fetch_defillama_chain_tvl, fetch_global_crypto_stats

    btc = next((c for c in board if c.token == "BTC"), None)
    eth = next((c for c in board if c.token == "ETH"), None)
    bullish = sum(1 for c in board if c.bias_class == "bullish")
    global_stats = fetch_global_crypto_stats()
    data = global_stats.get("data") or {}
    tvl = fetch_defillama_chain_tvl()
    return {
        "btc_bias": btc.bias if btc else "N/A",
        "eth_bias": eth.bias if eth else "N/A",
        "bullish_categories": bullish,
        "total_categories": len(board),
        "altcoin_season": "APPROACHING" if bullish >= max(1, len(board) // 2) else "NO",
        "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
        "market_cap_change_24h_pct": data.get("market_cap_change_percentage_24h_usd"),
        "defi_tvl_usd": tvl,
    }
