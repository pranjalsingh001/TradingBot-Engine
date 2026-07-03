"""
schemas.py — Pydantic models for request validation and response serialisation.
These are the contracts that the API endpoint enforces.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class IndicatorValues(BaseModel):
    """Raw computed indicator values returned alongside the signal."""
    rsi: float = Field(..., description="Latest RSI value (0–100)")
    ma: float = Field(..., description="Latest SMA value (e.g. 50-period)")
    ma200: float = Field(..., description="Long-term SMA value (e.g. 200-period)")
    atr: float = Field(..., description="Average True Range (volatility)")
    price: float = Field(..., description="Latest closing price")


class FactorBreakdown(BaseModel):
    """Individual factor scores that compose the final signal score."""
    momentum: float = Field(..., ge=-1.0, le=1.0, description="RSI-based momentum score [-1, 1]")
    trend: float = Field(..., ge=-1.0, le=1.0, description="Price vs MA50 trend score [-1, 1]")
    trend_strength: float = Field(..., description="MA50 vs MA200 trend strength: +1 or -1")
    volatility: float = Field(..., ge=-1.0, le=1.0, description="ATR-normalised volatility score [-1, 1]")


class WeightBreakdown(BaseModel):
    """Weights applied to each factor (regime-dependent)."""
    momentum: float = Field(..., description="Weight applied to momentum factor")
    trend: float = Field(..., description="Weight applied to trend factor")
    trend_strength: float = Field(..., description="Weight applied to trend_strength factor")
    volatility: float = Field(..., description="Weight applied to volatility factor")


class SignalResponse(BaseModel):
    """
    Full signal response returned by GET /signal/{symbol}.
    All fields are always present — never null in a success response.
    """
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT")
    interval: str = Field(..., description="Timeframe, e.g. 5m, 1h")
    signal: str = Field(..., description="BUY | SELL | HOLD")
    score: float = Field(..., description="Final weighted score [-1, 1]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence 0–1")
    regime: str = Field(..., description="TRENDING | SIDEWAYS")
    threshold: float = Field(..., description="Dynamic signal threshold used for this decision")
    indicators: IndicatorValues
    factors: FactorBreakdown
    weights: WeightBreakdown
    reason: List[str] = Field(..., description="Human-readable explanation array")


class ErrorResponse(BaseModel):
    """Returned when data is missing or the symbol is invalid."""
    symbol: str
    interval: str
    error: str
    signal: str = "HOLD"
    score: float = 0.0
    confidence: float = 0.0


# ── Risk Engine Models ────────────────────────────────────────────────────────

class AccountState(BaseModel):
    """Current account state passed to the risk engine."""
    balance: float = Field(..., gt=0, description="Current account balance in base currency")
    peak_balance: float = Field(..., gt=0, description="Highest balance ever recorded")
    active_trades: int = Field(0, ge=0, description="Number of currently open trades")
    current_exposure: float = Field(0.0, ge=0, description="Total position size of active trades")
    open_symbols: List[str] = Field(default_factory=list, description="Symbols with open positions")


class TrailingStopLevels(BaseModel):
    """Trailing stop levels for active trade management."""
    breakeven_trigger: float = Field(..., description="Price where stop moves to entry (1R profit)")
    trail_trigger: float = Field(..., description="Price where stop trails to lock 1R (2R profit)")
    breakeven_stop: float = Field(..., description="Stop loss at breakeven (= entry price)")
    trail_stop: float = Field(..., description="Trailing stop that locks 1R profit")


class RiskDecision(BaseModel):
    """Output of the risk engine — execute or skip."""
    execute: bool = Field(..., description="Whether to execute the trade")
    reason: str = Field(..., description="Why the trade was taken or skipped")
    signal: str = Field(..., description="BUY | SELL | HOLD")
    symbol: str = Field(..., description="Trading pair")
    interval: str = Field(..., description="Timeframe")
    position_size: float = Field(0.0, ge=0, description="Position size in base currency")
    position_units: float = Field(0.0, ge=0, description="Number of units/contracts to trade")
    entry_price: float = Field(0.0, ge=0, description="Entry price")
    stop_loss: float = Field(0.0, ge=0, description="Stop loss price")
    take_profit: float = Field(0.0, ge=0, description="Take profit price")
    risk_reward_ratio: float = Field(0.0, ge=0, description="Risk/reward ratio")
    risk_amount: float = Field(0.0, ge=0, description="Dollar amount risked on this trade")
    stop_loss_distance: float = Field(0.0, ge=0, description="Distance from entry to stop loss")
    exposure_after_trade: float = Field(0.0, ge=0, description="Total portfolio exposure after this trade")
    confidence: float = Field(0.0, ge=0, le=1.0, description="Signal confidence")
    regime: str = Field("", description="Market regime")
    trailing_stops: Optional[TrailingStopLevels] = Field(None, description="Trailing stop levels")


# ── Portfolio Engine Models ───────────────────────────────────────────────────

class SelectedTrade(BaseModel):
    """A trade selected and sized by the portfolio engine."""
    symbol: str
    signal: str
    score: float
    confidence: float
    position_size: float = Field(ge=0)
    risk_amount: float = Field(ge=0)
    stop_loss_distance: float = Field(ge=0)
    allocation_weight: float = Field(ge=0, description="Score-weighted allocation fraction")
    regime: str = ""
    category: str = Field("", description="Asset category for correlation control")


class PortfolioSummary(BaseModel):
    """Aggregate portfolio risk metrics."""
    total_positions: int = Field(ge=0)
    total_risk: float = Field(ge=0)
    max_allowed_risk: float = Field(ge=0)
    remaining_capacity: float = Field(ge=0)
    scale_factor: float = Field(1.0, description="Risk scaling factor applied (1.0 = no scaling)")


class PortfolioDecision(BaseModel):
    """Full portfolio allocation output."""
    selected_trades: List[SelectedTrade]
    portfolio: PortfolioSummary


# ── Evaluation Engine Models ──────────────────────────────────────────────────

class EvalSummary(BaseModel):
    """Core performance metrics."""
    total_trades: int = Field(ge=0)
    total_return_pct: float
    win_rate: float = Field(ge=0, le=1)
    profit_factor: float = Field(ge=0)
    expectancy: float
    max_drawdown_pct: float = Field(ge=0)
    sharpe_ratio: float


class EvalDistribution(BaseModel):
    """Trade distribution analysis."""
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int = Field(ge=0)
    max_consecutive_losses: int = Field(ge=0)


class EvalConsistency(BaseModel):
    """Consistency metrics — is profit distributed or concentrated?"""
    top_10_pct_contribution: float = Field(
        description="% of total profit contributed by top 10% of trades"
    )
    is_concentrated: bool = Field(
        description="True if top 10% contribute > 50% of profits"
    )


class EvalInterpretation(BaseModel):
    """Rule-based strategy quality assessment."""
    grade: str = Field(description="A / B / C / D / F")
    flags: List[str] = Field(description="Warning flags and observations")


class EvaluationResult(BaseModel):
    """Full evaluation output."""
    summary: EvalSummary
    distribution: EvalDistribution
    consistency: EvalConsistency
    interpretation: EvalInterpretation


class BacktestInput(BaseModel):
    """Input for the evaluation endpoint."""
    trades: List[dict] = Field(..., description="List of trade dicts with profit field")
    equity_curve: List[float] = Field(..., min_length=1, description="Account value over time")


# ── Paper Trading Models ──────────────────────────────────────────────────────

class PaperPosition(BaseModel):
    """An open or closed virtual position."""
    symbol: str
    side: str = Field(description="BUY or SELL")
    entry_price: float = Field(gt=0)
    position_size: float = Field(gt=0)
    stop_loss: float = Field(ge=0)
    take_profit: float = Field(ge=0)
    status: str = Field("OPEN", description="OPEN or CLOSED")
    unrealized_pnl: float = 0.0
    opened_at: str = ""
    closed_at: str = ""
    entry_metadata: dict = Field(default_factory=dict, description="Snapshot of indicators, regime, and confidence at entry")


class PaperTradeLog(BaseModel):
    """Record of a completed paper trade."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    position_size: float
    profit: float
    return_pct: float
    reason: str = Field(description="stop_loss | take_profit | manual")
    opened_at: str = ""
    closed_at: str = ""
    entry_metadata: dict = Field(default_factory=dict, description="Snapshot of indicators, regime, and confidence at entry")


class PaperStatus(BaseModel):
    """Snapshot of the paper trading account."""
    running: bool
    balance: float
    equity: float
    peak_balance: float
    open_positions: List[PaperPosition]
    total_trades: int
    win_rate: float
    total_return_pct: float
    max_drawdown_pct: float


class TradeInsight(BaseModel):
    """Deep metadata for an executed trade (Phase 2)."""
    trade_id: str
    symbol: str
    entry_price: float
    exit_price: float
    result: str = Field(description="WIN or LOSS")
    profit_percent: float
    market_regime: str
    rsi: float
    macd: float = 0.0 # Placeholder if not used
    atr: float
    confidence: float
    weights: dict
    trade_duration_minutes: int
    timestamp: str
