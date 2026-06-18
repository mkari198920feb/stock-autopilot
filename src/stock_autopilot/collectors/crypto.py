from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from stock_autopilot.collectors.coingecko import fetch_simple_prices, symbol_to_id


@dataclass
class CryptoMarketData:
    symbol: str
    price: float
    change_1h: float
    change_4h: float
    change_24h: float
    volume_24h: float
    rsi_14: float
    ma_20: float
    ma_50: float
    support: float
    resistance: float
    volatility_1h: float
    buy_pressure: float  # 0-1 proxy from candle structure
    hist_1h: pd.DataFrame = field(repr=False)


@dataclass
class MacroCryptoContext:
    dxy_change_1d: float | None
    us10y: float | None
    sp500_change_1d: float | None
    gold_change_1d: float | None


@dataclass
class CryptoContext:
    captured_at: datetime
    btc: CryptoMarketData
    eth: CryptoMarketData
    eth_btc_ratio: float
    eth_btc_change_4h: float
    fear_greed: int | None
    fear_greed_label: str
    macro: MacroCryptoContext
    session_name: str
    session_liquidity_note: str
    low_liquidity: bool


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    val = 100 - (100 / (1 + rs))
    v = val.iloc[-1]
    return float(v) if pd.notna(v) else 50.0


def _pct(from_price: float, to_price: float) -> float:
    if from_price <= 0:
        return 0.0
    return float(to_price / from_price - 1)


def _fetch_fear_greed() -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": "StockAutopilot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        item = data["data"][0]
        return int(item["value"]), str(item["value_classification"])
    except Exception:
        return None, "Unknown"


def _session_info(utc_hour: int, weekday: int) -> tuple[str, str, bool]:
    if weekday >= 5:
        return (
            "Weekend",
            "Lower liquidity — wider wicks and manipulation risk; confidence reduced.",
            True,
        )
    if 0 <= utc_hour < 7:
        return (
            "Asia",
            "Binance/OKX dominant — retail-driven, elevated short-term volatility.",
            False,
        )
    if 7 <= utc_hour < 13:
        return (
            "Europe",
            "Institutional overlap building — macro-sensitive handoff window.",
            utc_hour in (7, 8),
        )
    if 13 <= utc_hour < 21:
        return (
            "US",
            "Highest volume window — CME/ETF flows and macro headlines dominate.",
            utc_hour in (13, 14),
        )
    return (
        "Late US / Asia open",
        "Thin liquidity transition — reduce size or wait for session open.",
        True,
    )


def _load_asset(symbol: str) -> CryptoMarketData | None:
    asset = symbol.replace("-USD", "")
    coin_id = symbol_to_id(asset)
    cg_price = None
    cg_24h = None
    if coin_id:
        cg = fetch_simple_prices([coin_id], ttl=120)
        row = cg.get(coin_id) or {}
        if row.get("usd"):
            cg_price = float(row["usd"])
            ch = row.get("usd_24h_change")
            cg_24h = float(ch) / 100 if ch is not None else None

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", interval="1h", auto_adjust=True)
        if hist.empty or len(hist) < 24:
            hist = ticker.history(period="30d", interval="1h", auto_adjust=True)
        if hist.empty or len(hist) < 10:
            if cg_price:
                return CryptoMarketData(
                    symbol=asset,
                    price=cg_price,
                    change_1h=0.0,
                    change_4h=0.0,
                    change_24h=cg_24h or 0.0,
                    volume_24h=0.0,
                    rsi_14=50.0,
                    ma_20=cg_price,
                    ma_50=cg_price,
                    support=cg_price * 0.97,
                    resistance=cg_price * 1.03,
                    volatility_1h=0.01,
                    buy_pressure=0.5,
                    hist_1h=pd.DataFrame(),
                )
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        price = cg_price or float(closes.iloc[-1])
        if np.isnan(price) or price <= 0:
            price = float(closes.iloc[-2])

        c1 = float(closes.iloc[-2]) if len(closes) >= 2 else price
        c4 = float(closes.iloc[-5]) if len(closes) >= 5 else price
        c24 = float(closes.iloc[-25]) if len(closes) >= 25 else float(closes.iloc[0])

        window = closes.tail(48)
        support = float(window.min())
        resistance = float(window.max())

        recent = hist.tail(24)
        green = (recent["Close"] >= recent["Open"]).sum()
        buy_pressure = float(green / max(len(recent), 1))

        rets = closes.pct_change().dropna()
        vol_1h = float(rets.tail(12).std()) if len(rets) >= 12 else 0.01

        return CryptoMarketData(
            symbol=symbol.replace("-USD", ""),
            price=price,
            change_1h=_pct(c1, price),
            change_4h=_pct(c4, price),
            change_24h=cg_24h if cg_24h is not None else _pct(c24, price),
            volume_24h=float(hist["Volume"].tail(24).sum()),
            rsi_14=_rsi(closes),
            ma_20=float(closes.tail(20).mean()) if len(closes) >= 20 else price,
            ma_50=float(closes.tail(50).mean()) if len(closes) >= 50 else price,
            support=support,
            resistance=resistance,
            volatility_1h=vol_1h,
            buy_pressure=buy_pressure,
            hist_1h=hist,
        )
    except Exception:
        return None


def _macro_pct(symbol: str, period: str = "5d") -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if len(hist) < 2:
            return None
        return float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1)
    except Exception:
        return None


def _macro_level(symbol: str) -> float | None:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def fetch_crypto_context() -> CryptoContext:
    now = datetime.now(timezone.utc)
    btc = _load_asset("BTC-USD")
    eth = _load_asset("ETH-USD")
    if not btc or not eth:
        raise RuntimeError("Could not load BTC/ETH market data from Yahoo Finance")

    ratio_now = eth.price / btc.price if btc.price else 0
    ratio_4h_change = 0.0
    try:
        eth_hist = eth.hist_1h["Close"].dropna()
        btc_hist = btc.hist_1h["Close"].dropna()
        if len(eth_hist) >= 5 and len(btc_hist) >= 5:
            r_now = eth_hist.iloc[-1] / btc_hist.iloc[-1]
            r_prev = eth_hist.iloc[-5] / btc_hist.iloc[-5]
            ratio_4h_change = float(r_now / r_prev - 1) if r_prev else 0.0
    except Exception:
        ratio_4h_change = 0.0

    fg, fg_label = _fetch_fear_greed()
    session_name, session_note, low_liq = _session_info(now.hour, now.weekday())

    macro = MacroCryptoContext(
        dxy_change_1d=_macro_pct("DX-Y.NYB"),
        us10y=_macro_level("^TNX"),
        sp500_change_1d=_macro_pct("^GSPC"),
        gold_change_1d=_macro_pct("GC=F"),
    )

    return CryptoContext(
        captured_at=now,
        btc=btc,
        eth=eth,
        eth_btc_ratio=ratio_now,
        eth_btc_change_4h=ratio_4h_change,
        fear_greed=fg,
        fear_greed_label=fg_label,
        macro=macro,
        session_name=session_name,
        session_liquidity_note=session_note,
        low_liquidity=low_liq,
    )
