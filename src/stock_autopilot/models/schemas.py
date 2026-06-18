from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MacroSnapshot(BaseModel):
    captured_at: datetime
    regime: str
    risk_score: float
    summary: str
    indicators: dict[str, Any] = Field(default_factory=dict)


class NewsItem(BaseModel):
    symbol: str
    title: str
    publisher: str
    link: str
    published: str
    sentiment: float
    themes: list[str] = Field(default_factory=list)


class StockMetrics(BaseModel):
    symbol: str
    name: str
    region: str
    sector: str
    industry: str = ""
    price: float
    annualized_return: float
    volatility: float
    sharpe: float
    rsi: float
    pe_ratio: float | None
    pe_forward: float | None = None
    avg_volume: float
    momentum_3m: float
    momentum_12m: float
    beta: float | None = None
    ma_50: float | None = None
    ma_200: float | None = None
    macd_hist: float | None = None
    support: float | None = None
    resistance: float | None = None
    revenue_growth_yoy: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    ev_ebitda: float | None = None
    peg_ratio: float | None = None
    fcf_yield: float | None = None
    debt_to_equity: float | None = None
    roe: float | None = None
    roic: float | None = None


class ResearchNote(BaseModel):
    risk_tier: int
    risk_tier_label: str
    rating: str
    conviction: str
    price_target: float
    current_price: float
    upside_pct: float
    downside_pct: float
    industry: str
    thesis: list[str] = Field(default_factory=list)
    revenue_growth_yoy: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    pe_forward: float | None = None
    ev_ebitda: float | None = None
    peg_ratio: float | None = None
    fcf_yield: float | None = None
    debt_to_equity: float | None = None
    roe: float | None = None
    roic: float | None = None
    trend: str = "Neutral"
    rsi: float = 50.0
    macd_signal: str = "Neutral"
    support: float = 0.0
    resistance: float = 0.0
    pattern: str = ""
    catalyst_near: str = ""
    catalyst_medium: str = ""
    catalyst_long: str = ""
    risks: list[tuple[str, str]] = Field(default_factory=list)
    bull_case_price: float = 0.0
    bull_case_prob: int = 30
    bull_case_note: str = ""
    base_case_price: float = 0.0
    base_case_prob: int = 50
    base_case_note: str = ""
    bear_case_price: float = 0.0
    bear_case_prob: int = 20
    bear_case_note: str = ""
    size_conservative: str = "5%"
    size_balanced: str = "7%"
    size_aggressive: str = "4%"
    take_profit: str = ""
    stop_loss: str = ""
    thesis_breaker: str = ""
    desk_comment: str = ""


class StockPick(BaseModel):
    symbol: str
    name: str
    region: str
    sector: str
    score: float
    annualized_return_est: float
    rationale: str
    news_highlights: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    risk_note: str = ""
    research_note: ResearchNote | None = None
    research_note_text: str = ""


class ModelPortfolioHolding(BaseModel):
    symbol: str
    name: str
    region: str
    sector: str
    weight: float
    score: float
    annualized_return_est: float
    rationale: str


class ModelPortfolio(BaseModel):
    model_id: str
    label: str
    description: str
    benchmark: str
    cash_pct: float
    holdings: list[ModelPortfolioHolding]
    disclaimer: str = ""


class AgentRunResult(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    macro: MacroSnapshot
    picks: list[StockPick]
    model_portfolios: list[ModelPortfolio] = Field(default_factory=list)
    scanned: int
    status: str
    log: list[str] = Field(default_factory=list)


class CryptoSignalBreakdown(BaseModel):
    on_chain: str = "Neutral"
    derivatives: str = "Neutral"
    macro: str = "Neutral"
    sentiment: str = "Neutral"
    microstructure: str = "Neutral"
    session_timing: str = "Neutral"
    raw_scores: dict[str, float] = Field(default_factory=dict)


class CryptoHourlyPrediction(BaseModel):
    asset: str
    timestamp: datetime
    current_price: float
    prediction_window: str = "Next 1H"
    directional_bias: str
    bias_label: str
    bias_class: str
    confidence_pct: int
    confidence_label: str
    composite_score: float
    signals: CryptoSignalBreakdown
    key_driver: str
    risk_to_call: str
    target_upside: float
    target_upside_pct: float
    target_downside: float
    target_downside_pct: float
    invalidation: float
    desk_note: str
    top_signals: list[str] = Field(default_factory=list)
    card_text: str = ""
    eth_btc_note: str | None = None
    volatility_warning: str | None = None
    prior_outcome: str | None = None


class CryptoPulseSnapshot(BaseModel):
    pulse_id: str
    captured_at: datetime
    session_name: str
    session_liquidity_note: str
    opening_statement: str
    btc: CryptoHourlyPrediction
    eth: CryptoHourlyPrediction
    eth_btc_trend: str = "Neutral"
    btc_streak: int = 0
    eth_streak: int = 0


class IndiaMacroBar(BaseModel):
    nifty: float
    nifty_change_pct: float
    sensex: float
    sensex_change_pct: float
    india_vix: float | None = None
    vix_sentiment: str = "Neutral"
    inr_usd: float | None = None
    inr_change_pct: float | None = None
    brent_usd: float | None = None
    brent_impact: str = "Neutral"
    repo_rate: float = 6.50
    rbi_stance: str = "Neutral"
    nifty_pe: float | None = None
    pe_assessment: str = "Fair"
    ticker_text: str = ""


class IndiaEquityPick(BaseModel):
    symbol: str
    nse: str
    bse: str
    name: str
    sector: str
    industry: str
    market_cap_cr: float | None = None
    cap_segment: str
    score: float
    risk_tier: int
    risk_tier_label: str
    rating: str
    conviction: str
    cmp: float
    target_12m: float
    upside_pct: float
    thesis: list[str]
    financials: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    catalysts: dict[str, str] = Field(default_factory=dict)
    risks: list[tuple[str, str]] = Field(default_factory=list)
    tax_note: str = ""
    position_sizing: dict[str, str] = Field(default_factory=dict)
    exit_criteria: dict[str, str] = Field(default_factory=dict)
    desk_note: str = ""
    research_note_text: str = ""
    risk_class: str = "green"


class IndiaMFNote(BaseModel):
    fund_name: str
    amc: str
    category: str
    rating_label: str
    returns_1y: str
    returns_3y: str
    sharpe: str
    expense_direct: str
    who_should_invest: str
    tax_note: str
    sip_note: str
    desk_note: str
    risk_class: str = "green"


class IndiaFixedIncomeNote(BaseModel):
    instrument: str
    issuer: str
    instrument_type: str
    yield_label: str
    tenor: str
    credit_rating: str
    tax_note: str
    who_should_invest: str
    desk_note: str
    risk_class: str = "green"
    category: str  # bond or fd


class IndiaDeskSnapshot(BaseModel):
    desk_id: str
    captured_at: datetime
    opening_statement: str
    macro: IndiaMacroBar
    equities: list[IndiaEquityPick]
    mutual_funds: list[IndiaMFNote]
    bonds: list[IndiaFixedIncomeNote]
    fixed_deposits: list[IndiaFixedIncomeNote]
    disclaimer: str = "Consult your SEBI-registered financial advisor before investing."


class RegionalPickRow(BaseModel):
    rank: int
    symbol: str
    name: str
    exchange: str
    country: str
    risk_tier: int
    rating: str
    cmp: float
    target: float
    upside_pct: float
    score: float
    desk_note: str
    thesis_line: str = ""


class RegionalBoard(BaseModel):
    market_id: str
    label: str
    exchange: str
    country: str
    theme: str
    top_risk: str
    macro_pulse: dict[str, str] = Field(default_factory=dict)
    picks: list[RegionalPickRow] = Field(default_factory=list)
    avoids: list[RegionalPickRow] = Field(default_factory=list)


class CryptoCategoryPick(BaseModel):
    category: str
    tier: int
    token: str
    name: str
    bias: str
    bias_class: str
    timeframe: str
    confidence_pct: int
    price: float
    desk_note: str
    momentum_7d_pct: float | None = None


class GlobalDeskSnapshot(BaseModel):
    desk_id: str
    captured_at: datetime
    opening_statement: str
    signal_stack: dict = Field(default_factory=dict)
    macro_ticker: list[dict] = Field(default_factory=dict)
    regional_boards: list[RegionalBoard] = Field(default_factory=list)
    crypto_board: list[CryptoCategoryPick] = Field(default_factory=list)
    global_top_picks: list[RegionalPickRow] = Field(default_factory=list)
    disclaimer: str = "Research publisher only — not financial advice."


class MoverRow(BaseModel):
    rank: int
    symbol: str
    name: str
    cmp: float
    change_abs: float
    change_pct: float
    volume_vs_avg_pct: float = 100.0
    sector: str = "—"
    reason: str = ""
    contrarian_score: int | None = None


class IndexQuote(BaseModel):
    label: str
    symbol: str
    value: float
    change_abs: float
    change_pct: float
    direction: str = "flat"


class SectorHeatCell(BaseModel):
    sector: str
    change_pct: float
    reason: str = ""


class MarketPulseBoard(BaseModel):
    market_id: str
    label: str
    flag: str = "🌍"
    timezone: str = "UTC"
    session: str = "open"
    captured_at: datetime
    indices: list[IndexQuote] = Field(default_factory=list)
    top_gainers: list[MoverRow] = Field(default_factory=list)
    top_losers: list[MoverRow] = Field(default_factory=list)
    week_52_highs: list[MoverRow] = Field(default_factory=list)
    week_52_lows: list[MoverRow] = Field(default_factory=list)
    all_time_highs: list[MoverRow] = Field(default_factory=list)
    upper_circuits: list[MoverRow] = Field(default_factory=list)
    lower_circuits: list[MoverRow] = Field(default_factory=list)
    volume_leaders: list[MoverRow] = Field(default_factory=list)
    sector_heatmap: list[SectorHeatCell] = Field(default_factory=list)
    macro_pulse: dict = Field(default_factory=dict)
    tomorrow_setup: str = ""
    breadth: dict = Field(default_factory=dict)


class CryptoMarketPulseBoard(BaseModel):
    captured_at: datetime
    total_market_cap_usd: float = 0.0
    market_cap_change_24h_pct: float = 0.0
    btc_dominance_pct: float = 0.0
    eth_dominance_pct: float = 0.0
    fear_greed_label: str = "Neutral"
    top_by_mcap: list[dict] = Field(default_factory=list)
    top_gainers_24h: list[dict] = Field(default_factory=list)
    top_losers_24h: list[dict] = Field(default_factory=list)
    week_52_highs: list[dict] = Field(default_factory=list)
    week_52_lows: list[dict] = Field(default_factory=list)
    ath_alerts: list[dict] = Field(default_factory=list)
    volume_leaders: list[dict] = Field(default_factory=list)
    category_performance: list[dict] = Field(default_factory=list)
    tomorrow_setup: str = ""


class MarketPulseSnapshot(BaseModel):
    pulse_id: str
    captured_at: datetime
    session_label: str
    opening_statement: str
    boards: list[MarketPulseBoard] = Field(default_factory=list)
    crypto: CryptoMarketPulseBoard | None = None
    india_eod_breadth: dict = Field(default_factory=dict)


class DeepStockBrief(BaseModel):
    symbol: str
    name: str
    exchange: str
    sector: str
    industry: str
    currency: str
    cmp: float
    change_pct: float
    change_abs: float
    week_52_high: float
    week_52_low: float
    week_52_high_dist_pct: float
    week_52_low_dist_pct: float
    market_cap: float | None = None
    cap_segment: str = "—"
    rating: str
    target_price: float
    upside_pct: float
    risk_tier: int
    conviction: str
    horizon: str
    verdict: str
    why_recommending: str
    top_reasons: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    business_snapshot: str = ""
    pillars: dict = Field(default_factory=dict)
    financials_glance: dict = Field(default_factory=dict)
    valuation: dict = Field(default_factory=dict)
    technical: dict = Field(default_factory=dict)
    ownership: dict = Field(default_factory=dict)
    catalysts: list[dict] = Field(default_factory=list)
    peer_comparison: dict = Field(default_factory=dict)
    position_guide: dict = Field(default_factory=dict)
    analyst_consensus: dict = Field(default_factory=dict)
    desk_verdict: str = ""
    card_text: str = ""
    generated_at: datetime
    trigger_context: str = ""
