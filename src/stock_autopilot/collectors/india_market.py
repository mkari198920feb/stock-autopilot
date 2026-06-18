from __future__ import annotations

from stock_autopilot.collectors.market import batch_fetch_metrics
from stock_autopilot.models.schemas import StockMetrics


CAP_TIER_1 = {
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "ITC.NS", "LT.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "HINDUNILVR.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "NTPC.NS",
    "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS", "WIPRO.NS", "ULTRACEMCO.NS",
}


def nse_symbol(yahoo_symbol: str) -> str:
    return yahoo_symbol.replace(".NS", "").replace(".BO", "")


def cap_segment(symbol: str, market_cap: float | None) -> str:
    if symbol in CAP_TIER_1:
        return "Large Cap"
    if market_cap and market_cap > 50_000 * 1e7:
        return "Large Cap"
    if market_cap and market_cap > 10_000 * 1e7:
        return "Mid Cap"
    if market_cap and market_cap > 2_000 * 1e7:
        return "Small Cap"
    return "Mid Cap"


def fetch_india_universe(cfg: dict) -> list[StockMetrics]:
    india = cfg.get("india_desk", {})
    symbols = india.get("nse_universe") or []
    region_map = {s: "india" for s in symbols}
    lookback = cfg.get("agent", {}).get("lookback_days", 252)
    min_vol = india.get("min_avg_volume", 100_000)
    metrics = batch_fetch_metrics(symbols, region_map, lookback)
    return [m for m in metrics if m.avg_volume >= min_vol]
