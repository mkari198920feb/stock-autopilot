from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class CommodityRaw:
    symbol: str
    name: str
    category_id: str
    category_label: str
    unit: str
    price: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    week_52_high: float | None
    week_52_low: float | None
    rsi_14: float
    ma_20: float | None
    ma_50: float | None
    volume: float | None


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
    return float((to_price / from_price - 1) * 100)


def _fetch_one(entry: dict, category_id: str, category_label: str) -> CommodityRaw | None:
    symbol = entry.get("symbol") or entry.get("ticker")
    if not symbol:
        return None
    name = entry.get("name", symbol)
    unit = entry.get("unit", "$")
    try:
        hist = yf.Ticker(symbol).history(period="1y", auto_adjust=True)
        if hist.empty or len(hist) < 5:
            return None
        closes = hist["Close"].dropna()
        price = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else price
        week_ref = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
        month_ref = float(closes.iloc[-22]) if len(closes) >= 22 else float(closes.iloc[0])
        ma_20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
        ma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
        w52h = float(closes.max())
        w52l = float(closes.min())
        vol = float(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else None
        return CommodityRaw(
            symbol=symbol,
            name=name,
            category_id=category_id,
            category_label=category_label,
            unit=unit,
            price=round(price, 4),
            change_1d_pct=round(_pct(prev, price), 2),
            change_1w_pct=round(_pct(week_ref, price), 2),
            change_1m_pct=round(_pct(month_ref, price), 2),
            week_52_high=round(w52h, 4),
            week_52_low=round(w52l, 4),
            rsi_14=round(_rsi(closes), 1),
            ma_20=round(ma_20, 4) if ma_20 else None,
            ma_50=round(ma_50, 4) if ma_50 else None,
            volume=vol,
        )
    except Exception:
        return None


def fetch_commodities_universe(categories: dict) -> list[CommodityRaw]:
    rows: list[CommodityRaw] = []
    for cat_id, cat in (categories or {}).items():
        label = cat.get("label", cat_id.replace("_", " ").title())
        for entry in cat.get("symbols") or []:
            if isinstance(entry, str):
                entry = {"symbol": entry, "name": entry}
            raw = _fetch_one(entry, cat_id, label)
            if raw:
                rows.append(raw)
    return rows
