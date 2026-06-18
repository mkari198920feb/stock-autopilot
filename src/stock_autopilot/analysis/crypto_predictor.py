from __future__ import annotations

from datetime import datetime

from stock_autopilot.collectors.crypto import CryptoContext, CryptoMarketData
from stock_autopilot.models.schemas import (
    CryptoHourlyPrediction,
    CryptoPulseSnapshot,
    CryptoSignalBreakdown,
)
from stock_autopilot.universe import brand_cfg

WEIGHTS = {
    "on_chain": 0.25,
    "derivatives": 0.25,
    "macro": 0.20,
    "sentiment": 0.15,
    "microstructure": 0.10,
    "session_timing": 0.05,
}


def _label_score(score: float) -> str:
    if score >= 0.25:
        return "Bullish"
    if score <= -0.25:
        return "Bearish"
    return "Neutral"


def _session_label(score: float) -> str:
    if score >= 0.2:
        return "Favorable"
    if score <= -0.2:
        return "Risk"
    return "Neutral"


def _bias_from_composite(score: float) -> tuple[str, str, str]:
    if score >= 0.6:
        return "STRONG BULLISH BIAS", "🟢 BULLISH", "bullish"
    if score >= 0.2:
        return "MILD BULLISH BIAS", "🟢 BULLISH", "bullish"
    if score <= -0.6:
        return "STRONG BEARISH BIAS", "🔴 BEARISH", "bearish"
    if score <= -0.2:
        return "MILD BEARISH BIAS", "🔴 BEARISH", "bearish"
    return "NEUTRAL / CHOPPY", "🟡 NEUTRAL", "neutral"


def _confidence(score: float, low_liquidity: bool, conflict: bool) -> tuple[int, str]:
    base = min(92, int(45 + abs(score) * 50))
    if low_liquidity:
        base = max(35, base - 12)
    if conflict:
        base = max(30, base - 15)
    label = "High" if base >= 72 else "Medium" if base >= 52 else "Low"
    return base, label


def _score_on_chain(data: CryptoMarketData) -> float:
    s = 0.0
    if data.price > data.ma_20 > data.ma_50:
        s += 0.5
    elif data.price < data.ma_20 < data.ma_50:
        s -= 0.5
    if data.change_24h > 0.02:
        s += 0.25
    elif data.change_24h < -0.02:
        s -= 0.25
    if data.volume_24h > 0 and data.change_1h > 0:
        s += 0.15
    return max(-1.0, min(1.0, s))


def _score_derivatives(data: CryptoMarketData) -> float:
    s = 0.0
    if data.rsi_14 > 68:
        s -= 0.35
    elif data.rsi_14 < 32:
        s += 0.35
    if data.change_4h > 0.015 and data.volatility_1h < 0.015:
        s += 0.3
    elif data.change_4h < -0.015 and data.volatility_1h > 0.02:
        s -= 0.3
    if data.change_1h * data.change_4h > 0:
        s += 0.2 if data.change_1h > 0 else -0.2
    return max(-1.0, min(1.0, s))


def _score_macro(ctx: CryptoContext) -> float:
    m = ctx.macro
    s = 0.0
    if m.dxy_change_1d is not None:
        s -= 0.35 if m.dxy_change_1d > 0.003 else 0.25 if m.dxy_change_1d < -0.003 else 0
    if m.sp500_change_1d is not None:
        s += 0.35 if m.sp500_change_1d > 0.005 else -0.3 if m.sp500_change_1d < -0.005 else 0
    if m.us10y is not None and m.us10y > 4.5:
        s -= 0.15
    if m.gold_change_1d is not None and m.gold_change_1d > 0.01:
        s -= 0.1
    return max(-1.0, min(1.0, s))


def _score_sentiment(ctx: CryptoContext) -> float:
    if ctx.fear_greed is None:
        return 0.0
    fg = ctx.fear_greed
    if fg <= 20:
        return 0.6
    if fg <= 35:
        return 0.25
    if fg >= 80:
        return -0.55
    if fg >= 65:
        return -0.2
    return 0.0


def _score_microstructure(data: CryptoMarketData) -> float:
    s = (data.buy_pressure - 0.5) * 1.6
    if data.change_1h > 0.005:
        s += 0.2
    elif data.change_1h < -0.005:
        s -= 0.2
    return max(-1.0, min(1.0, s))


def _score_session(ctx: CryptoContext) -> float:
    if ctx.session_name == "US":
        return 0.3
    if ctx.session_name == "Weekend":
        return -0.4
    if ctx.low_liquidity:
        return -0.25
    if ctx.session_name == "Asia":
        return 0.1
    return 0.0


def _composite(raw: dict[str, float]) -> float:
    return sum(raw[k] * WEIGHTS[k] for k in WEIGHTS)


def _near_liquidation_cluster(data: CryptoMarketData) -> bool:
    dist_sup = abs(data.price - data.support) / data.price
    dist_res = abs(data.resistance - data.price) / data.price
    return min(dist_sup, dist_res) < 0.02


def _format_card(pred: CryptoHourlyPrediction) -> str:
    sig = pred.signals
    header = brand_cfg()["crypto_header"]
    return f"""╔══════════════════════════════════════════════════╗
║   {header:<47} ║
║   Asset: {pred.asset:<6} |  Timestamp: {pred.timestamp.strftime('%H:%M UTC')} ║
╠══════════════════════════════════════════════════╣
║ CURRENT PRICE     : ${pred.current_price:,.2f}
║ PREDICTION WINDOW : {pred.prediction_window}
║ DIRECTIONAL BIAS  : {pred.bias_label}
║ CONFIDENCE SCORE  : {pred.confidence_pct}% ({pred.confidence_label})
╠══════════════════════════════════════════════════╣
║ SIGNAL BREAKDOWN
║  On-Chain       : {sig.on_chain}
║  Derivatives    : {sig.derivatives}
║  Macro          : {sig.macro}
║  Sentiment      : {sig.sentiment}
║  Microstructure : {sig.microstructure}
║  Session Timing : {sig.session_timing}
╠══════════════════════════════════════════════════╣
║ KEY DRIVER       : {pred.key_driver}
║ RISK TO CALL     : {pred.risk_to_call}
╠══════════════════════════════════════════════════╣
║ PRICE TARGETS
║  Target Upside  : ${pred.target_upside:,.2f} (+{pred.target_upside_pct:.1f}%)
║  Target Downside: ${pred.target_downside:,.2f} (-{pred.target_downside_pct:.1f}%)
║  Invalidation   : ${pred.invalidation:,.2f}
╠══════════════════════════════════════════════════╣
║ DESK NOTE: {pred.desk_note}
╚══════════════════════════════════════════════════╝"""


def _build_prediction(
    asset: str,
    data: CryptoMarketData,
    ctx: CryptoContext,
    eth_btc_note: str | None = None,
    prior_outcome: str | None = None,
) -> CryptoHourlyPrediction:
    raw = {
        "on_chain": _score_on_chain(data),
        "derivatives": _score_derivatives(data),
        "macro": _score_macro(ctx),
        "sentiment": _score_sentiment(ctx),
        "microstructure": _score_microstructure(data),
        "session_timing": _score_session(ctx),
    }
    composite = _composite(raw)

    bullish_n = sum(1 for v in raw.values() if v > 0.2)
    bearish_n = sum(1 for v in raw.values() if v < -0.2)
    conflict = bullish_n >= 2 and bearish_n >= 2
    if conflict:
        composite = composite * 0.35

    bias, bias_label, bias_class = _bias_from_composite(composite)
    conf_pct, conf_label = _confidence(composite, ctx.low_liquidity, conflict)

    mult = 1.0 + abs(composite) * 0.012
    if bias_class == "bullish":
        target_up = data.price * mult
        target_dn = data.price * (1 - 0.008 - abs(composite) * 0.006)
        invalidation = data.support
    elif bias_class == "bearish":
        target_up = data.price * (1 + 0.008 + abs(composite) * 0.006)
        target_dn = data.price * (2 - mult)
        invalidation = data.resistance
    else:
        target_up = data.price * 1.006
        target_dn = data.price * 0.994
        invalidation = data.support if composite >= 0 else data.resistance

    sorted_signals = sorted(raw.items(), key=lambda x: abs(x[1]), reverse=True)
    top = [f"{k.replace('_', ' ').title()} ({v:+.2f})" for k, v in sorted_signals[:2]]
    key_driver = f"{top[0]} and {top[1]} drive the {asset} hourly bias." if len(top) >= 2 else top[0]

    risk = f"Break below ${invalidation:,.0f} invalidates the call." if bias_class != "bearish" else f"Sustained move above ${invalidation:,.0f} invalidates the bearish view."
    if ctx.macro.dxy_change_1d and ctx.macro.dxy_change_1d > 0.005:
        risk += " Stronger DXY is the main macro risk."

    vol_warn = None
    if _near_liquidation_cluster(data):
        vol_warn = "HIGH VOLATILITY RISK — price within ~2% of a liquidation cluster (support/resistance proxy)."

    desk = (
        f"Market is pricing {'continuation' if data.change_1h * composite > 0 else 'mean reversion'}; "
        f"signal stack says {bias.lower()} with {conf_label.lower()} conviction."
    )

    pred = CryptoHourlyPrediction(
        asset=asset,
        timestamp=ctx.captured_at,
        current_price=round(data.price, 2),
        prediction_window="Next 1H / 2H / 4H",
        directional_bias=bias,
        bias_label=bias_label,
        bias_class=bias_class,
        confidence_pct=conf_pct,
        confidence_label=conf_label,
        composite_score=round(composite, 3),
        signals=CryptoSignalBreakdown(
            on_chain=_label_score(raw["on_chain"]),
            derivatives=_label_score(raw["derivatives"]),
            macro=_label_score(raw["macro"]),
            sentiment=_label_score(raw["sentiment"]),
            microstructure=_label_score(raw["microstructure"]),
            session_timing=_session_label(raw["session_timing"]),
            raw_scores={k: round(v, 3) for k, v in raw.items()},
        ),
        key_driver=key_driver,
        risk_to_call=risk,
        target_upside=round(target_up, 2),
        target_upside_pct=round((target_up / data.price - 1) * 100, 2),
        target_downside=round(target_dn, 2),
        target_downside_pct=round((1 - target_dn / data.price) * 100, 2),
        invalidation=round(invalidation, 2),
        desk_note=desk,
        top_signals=top,
        eth_btc_note=eth_btc_note,
        volatility_warning=vol_warn,
        prior_outcome=prior_outcome,
    )
    pred.card_text = _format_card(pred)
    return pred


def _streak_label(asset: str, bias_class: str, streak: int) -> str:
    if streak <= 1:
        return ""
    emoji = "✅" if bias_class != "neutral" else "➖"
    return f"{asset}: {streak} consecutive {bias_class.upper()} calls {emoji}"


def build_crypto_pulse(
    ctx: CryptoContext,
    prior: CryptoPulseSnapshot | None = None,
    btc_streak: int = 0,
    eth_streak: int = 0,
) -> CryptoPulseSnapshot:
    eth_btc_trend = "Neutral"
    eth_note = None
    if ctx.eth_btc_change_4h > 0.008:
        eth_btc_trend = "ETH outperforming BTC"
        eth_note = "ETH/BTC ratio rising — potential altcoin strength / beta amplification vs BTC."
    elif ctx.eth_btc_change_4h < -0.008:
        eth_btc_trend = "ETH lagging BTC"
        eth_note = "ETH/BTC ratio falling — ETH may underperform BTC beta in this window."

    btc_prior = eth_prior = None
    if prior:
        btc_prior = _score_prior_outcome(prior.btc, ctx.btc.price)
        eth_prior = _score_prior_outcome(prior.eth, ctx.eth.price)

    btc_pred = _build_prediction("BTC", ctx.btc, ctx, prior_outcome=btc_prior)
    eth_pred = _build_prediction("ETH", ctx.eth, ctx, eth_btc_note=eth_note, prior_outcome=eth_prior)

    if prior:
        if prior.btc.bias_class == btc_pred.bias_class and btc_pred.bias_class != "neutral":
            btc_streak = btc_streak + 1
        elif btc_pred.bias_class != "neutral":
            btc_streak = 1
        else:
            btc_streak = 0
        if prior.eth.bias_class == eth_pred.bias_class and eth_pred.bias_class != "neutral":
            eth_streak = eth_streak + 1
        elif eth_pred.bias_class != "neutral":
            eth_streak = 1
        else:
            eth_streak = 0

    name = brand_cfg()["brand_name"]
    opening = (
        f"{name} Crypto Desk is now live. Aggregating on-chain proxies, derivatives structure, "
        "macro cross-asset signals, sentiment, and spot microstructure for hourly BTC/ETH calls. "
        f"Current session: {ctx.session_name} — {ctx.session_liquidity_note}"
    )

    pulse_id = ctx.captured_at.strftime("%Y%m%d%H") + "-crypto"
    return CryptoPulseSnapshot(
        pulse_id=pulse_id,
        captured_at=ctx.captured_at,
        session_name=ctx.session_name,
        session_liquidity_note=ctx.session_liquidity_note,
        opening_statement=opening,
        btc=btc_pred,
        eth=eth_pred,
        eth_btc_trend=eth_btc_trend,
        btc_streak=btc_streak,
        eth_streak=eth_streak,
    )


def _score_prior_outcome(prior: CryptoHourlyPrediction, current_price: float) -> str:
    move = (current_price / prior.current_price - 1) if prior.current_price else 0
    predicted_up = prior.bias_class == "bullish"
    predicted_down = prior.bias_class == "bearish"
    if prior.bias_class == "neutral":
        return f"Prior NEUTRAL — move {move*100:+.2f}% (no directional call)"
    if predicted_up and move > 0.002:
        return f"Prior BULLISH — HIT ✅ ({move*100:+.2f}%)"
    if predicted_down and move < -0.002:
        return f"Prior BEARISH — HIT ✅ ({move*100:+.2f}%)"
    if abs(move) <= 0.002:
        return f"Prior {prior.bias_class.upper()} — PARTIAL (~flat {move*100:+.2f}%)"
    return f"Prior {prior.bias_class.upper()} — MISS ❌ ({move*100:+.2f}%)"
