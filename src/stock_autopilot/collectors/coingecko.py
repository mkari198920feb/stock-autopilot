from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json

BASE = "https://api.coingecko.com/api/v3"
UA = {"User-Agent": "UptickAlpha/1.0 (research-autopilot)"}

# Yahoo ticker suffix → CoinGecko id
TICKER_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "ATOM": "cosmos",
    "NEAR": "near",
    "APT": "aptos",
    "MATIC": "matic-network",
    "POL": "matic-network",
    "ARB": "arbitrum",
    "OP": "optimism",
    "UNI": "uniswap",
    "AAVE": "aave",
    "LINK": "chainlink",
    "MKR": "maker",
    "FET": "fetch-ai",
    "RNDR": "render-token",
    "GRT": "the-graph",
    "TAO": "bittensor",
    "FIL": "filecoin",
    "AR": "arweave",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
}


def symbol_to_id(symbol: str) -> str | None:
    sym = symbol.upper().replace("-USD", "").replace("USDT", "")
    return TICKER_TO_ID.get(sym)


def _fetch_url(url: str, timeout: int = 12) -> Any:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_simple_prices(coin_ids: list[str], ttl: int = 300) -> dict[str, dict]:
    if not coin_ids:
        return {}
    key = "cg:simple:" + ",".join(sorted(set(coin_ids)))
    hit = cache_get_json(key)
    if isinstance(hit, dict):
        return hit

    ids = ",".join(sorted(set(coin_ids)))
    url = (
        f"{BASE}/simple/price?ids={urllib.parse.quote(ids)}"
        "&vs_currencies=usd&include_24hr_change=true&include_7d_change=true&include_market_cap=true"
    )
    try:
        data = _fetch_url(url)
        cache_set_json(key, data, ttl)
        return data
    except Exception:
        return {}


def fetch_market_batch(coin_ids: list[str], ttl: int = 600) -> list[dict]:
    if not coin_ids:
        return []
    key = "cg:markets:" + ",".join(sorted(set(coin_ids)))
    hit = cache_get_json(key)
    if isinstance(hit, list):
        return hit

    ids = ",".join(sorted(set(coin_ids)))
    url = (
        f"{BASE}/coins/markets?vs_currency=usd&ids={urllib.parse.quote(ids)}"
        "&order=market_cap_desc&sparkline=false&price_change_percentage=24h,7d,30d"
    )
    try:
        data = _fetch_url(url)
        if isinstance(data, list):
            cache_set_json(key, data, ttl)
            return data
    except Exception:
        pass
    return []


def fetch_coin_detail(coin_id: str, ttl: int = 3600) -> dict | None:
    key = f"cg:coin:{coin_id}"
    hit = cache_get_json(key)
    if isinstance(hit, dict):
        return hit
    url = (
        f"{BASE}/coins/{urllib.parse.quote(coin_id)}"
        "?localization=false&tickers=false&community_data=true&developer_data=true"
    )
    try:
        data = _fetch_url(url)
        if isinstance(data, dict):
            cache_set_json(key, data, ttl)
            return data
    except Exception:
        return None
    return None


def fetch_global_crypto_stats(ttl: int = 600) -> dict:
    key = "cg:global"
    hit = cache_get_json(key)
    if isinstance(hit, dict):
        return hit
    try:
        data = _fetch_url(f"{BASE}/global")
        if isinstance(data, dict):
            cache_set_json(key, data, ttl)
            return data
    except Exception:
        pass
    return {}


def fetch_defillama_chain_tvl(ttl: int = 900) -> float | None:
    key = "llama:chains"
    hit = cache_get_json(key)
    if isinstance(hit, dict) and hit.get("total_tvl") is not None:
        return float(hit["total_tvl"])
    try:
        chains = _fetch_url("https://api.llama.fi/v2/chains", timeout=15)
        if isinstance(chains, list):
            total = sum(float(c.get("tvl") or 0) for c in chains)
            cache_set_json(key, {"total_tvl": total}, ttl)
            return total
    except Exception:
        pass
    return None


def metrics_for_symbol(symbol: str, entry: dict | None = None) -> dict | None:
    coin_id = (entry or {}).get("coingecko_id") or symbol_to_id(symbol)
    if not coin_id:
        return None
    prices = fetch_simple_prices([coin_id])
    row = prices.get(coin_id)
    if not row:
        markets = fetch_market_batch([coin_id])
        if markets:
            m = markets[0]
            return {
                "price": float(m.get("current_price") or 0),
                "chg_24h": m.get("price_change_percentage_24h_in_currency"),
                "chg_7d": m.get("price_change_percentage_7d_in_currency"),
                "market_cap": m.get("market_cap"),
                "rank": m.get("market_cap_rank"),
                "coin_id": coin_id,
            }
        return None
    return {
        "price": float(row.get("usd") or 0),
        "chg_24h": row.get("usd_24h_change"),
        "chg_7d": row.get("usd_7d_change"),
        "market_cap": row.get("usd_market_cap"),
        "coin_id": coin_id,
    }
