"""
models.py — Cross-phase data contracts for the Adaptive Quantitative Trading System.

All phases share these dataclasses to ensure interoperability.
Defined once here; imported everywhere.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd


# ── Phase A: MarketSnapshot ──────────────────────────────────────────────────

@dataclass
class MarketSnapshot:
    """
    Unified multi-timeframe market state.
    Produced by candle_loader, consumed by all downstream phases.
    """
    symbol: str
    timestamp: datetime
    candles_15m: pd.DataFrame   # columns: open, high, low, close, volume
    candles_5m: pd.DataFrame
    candles_1m: pd.DataFrame    # may be empty if use_1m_refinement=False
    regime: str = "UNKNOWN"     # set by regime_engine (Phase A)
    bias_15m: str = "neutral"   # "bullish" | "bearish" | "neutral" (Phase A)
    atr_5m: float = 0.0        # set by Phase A
    features: Optional[Any] = None  # set by Phase D (FeatureSet)


# ── Phase B: Signal ──────────────────────────────────────────────────────────

@dataclass
class Signal:
    """
    Raw trade signal produced by a strategy archetype.
    Consumed by the risk engine (Phase C).
    """
    direction: str          # "LONG" | "SHORT" | "NONE"
    confidence: float       # 0.0 – 1.0
    entry_price: float
    raw_sl: float           # pre-risk-engine stop loss price
    raw_tp: float           # pre-risk-engine take profit price
    strategy_id: str
    regime: str
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())


# ── Phase C: SizedSignal ─────────────────────────────────────────────────────

@dataclass
class SizedSignal:
    """
    Signal after risk engine processing with final SL, TP, and quantity.
    """
    signal: Signal
    sl: float               # ATR-adjusted stop loss
    tp: float               # ATR-adjusted take profit
    quantity: float          # computed by position sizer
    dollar_risk: float
    regime: str


# ── Phase C: PortfolioState ──────────────────────────────────────────────────

@dataclass
class PortfolioState:
    """Current portfolio state for risk calculations."""
    equity: float
    peak_equity: float
    day_start_equity: float
    consecutive_losses: int = 0
    daily_drawdown_pct: float = 0.0
    is_paused: bool = False
    pause_reason: str = ""
    recent_regimes: List[str] = field(default_factory=list)


# ── Phase B/G: TradeResult ───────────────────────────────────────────────────

@dataclass
class TradeResult:
    """
    Complete record of a closed trade.
    Used by intelligence layer (Phase E) and backtesting (Phase G).
    """
    trade_id: str
    strategy_id: str
    regime: str
    direction: str
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    quantity: float
    gross_pnl: float
    net_pnl: float          # after fees
    fee_cost: float = 0.0
    slippage_cost: float = 0.0
    hold_time_min: float = 0.0
    mfe: float = 0.0        # Maximum Favorable Excursion
    mae: float = 0.0        # Maximum Adverse Excursion
    result: str = "BREAKEVEN"  # "WIN" | "LOSS" | "BREAKEVEN"
    r_multiple: float = 0.0


# ── Phase D: Feature containers ──────────────────────────────────────────────

@dataclass
class LiquiditySweepResult:
    """Result of liquidity sweep detection."""
    sweep_detected: bool = False
    sweep_direction: Optional[str] = None  # "upside" | "downside" | None
    sweep_magnitude_atr: float = 0.0


@dataclass
class VolatilityFeatures:
    """Volatility compression/expansion metrics."""
    bb_width: float = 0.0
    bb_width_percentile: float = 0.0
    atr_ratio: float = 1.0
    is_compressed: bool = False
    compression_bars: int = 0


@dataclass
class TrendPersistenceFeatures:
    """Trend quality and consistency metrics."""
    directional_ratio: float = 0.0
    avg_candle_body_pct: float = 0.0
    trend_acceleration: float = 0.0
    persistence_score: float = 0.0


@dataclass
class VolumeFeatures:
    """Volume analysis results."""
    buy_volume_ratio: float = 0.5
    volume_delta: float = 0.0
    volume_trend: str = "flat"       # "increasing" | "decreasing" | "flat"
    relative_volume: float = 1.0
    volume_climax: bool = False


@dataclass
class StructureLevels:
    """Support and resistance levels."""
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    nearest_resistance: float = 0.0
    nearest_support: float = 0.0
    distance_to_resistance_atr: float = float('inf')
    distance_to_support_atr: float = float('inf')


@dataclass
class FeatureSet:
    """Aggregated features from all feature modules (Phase D)."""
    liquidity: LiquiditySweepResult = field(default_factory=LiquiditySweepResult)
    volatility: VolatilityFeatures = field(default_factory=VolatilityFeatures)
    trend: TrendPersistenceFeatures = field(default_factory=TrendPersistenceFeatures)
    volume: VolumeFeatures = field(default_factory=VolumeFeatures)
    structure: StructureLevels = field(default_factory=StructureLevels)


# ── Phase E: Intelligence layer models ───────────────────────────────────────

@dataclass
class StrategyHealth:
    """Health assessment for a single strategy."""
    strategy_id: str
    evaluation_period: str       # "last_20_trades" | "last_7_days"
    trade_count: int = 0
    win_rate: float = 0.0
    expectancy: float = 0.0
    avg_rr: float = 0.0
    max_consecutive_losses: int = 0
    drawdown_in_period: float = 0.0
    health_score: float = 100.0  # 0–100
    health_status: str = "HEALTHY"  # "HEALTHY" | "DEGRADING" | "CRITICAL"
    recommendation: Optional[str] = None


@dataclass
class RegimeReliability:
    """Regime classifier reliability assessment."""
    evaluation_window_hours: int = 24
    total_regime_changes: int = 0
    avg_regime_duration_bars: float = 0.0
    regime_flip_rate: float = 0.0
    unstable_periods: int = 0
    reliability_score: float = 1.0
    is_reliable: bool = True


@dataclass
class TradeQuality:
    """Trade quality assessment metrics."""
    avg_confidence: float = 0.0
    low_confidence_rate: float = 0.0
    trade_frequency_per_day: float = 0.0
    avg_hold_time_minutes: float = 0.0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    mfe_mae_ratio: float = 1.0


@dataclass
class RiskEvent:
    """A detected risk escalation event."""
    event_type: str     # "VOLATILITY_INSTABILITY" | "CORRELATED_LOSSES" | etc.
    severity: str       # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    recommended_action: str = ""


@dataclass
class Recommendation:
    """An actionable recommendation from the intelligence layer."""
    source_evaluator: str
    priority: str       # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    title: str
    description: str
    proposed_change: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"  # "PENDING" | "APPROVED" | "REJECTED" | "APPLIED" | "FROZEN" | "CAPPED"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    approved_by: Optional[str] = None
    applied_at: Optional[datetime] = None


# ── Phase G: Backtesting models ──────────────────────────────────────────────

@dataclass
class EquityCurveMetrics:
    """Comprehensive equity curve analytics."""
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    recovery_factor: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    avg_win_R: float = 0.0
    avg_loss_R: float = 0.0
    expectancy_R: float = 0.0
    total_trades: int = 0
    avg_trades_per_day: float = 0.0
    longest_win_streak: int = 0
    longest_loss_streak: int = 0


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation results."""
    median_final_equity: float = 0.0
    p5_final_equity: float = 0.0
    p95_final_equity: float = 0.0
    median_max_drawdown: float = 0.0
    p95_max_drawdown: float = 0.0
    ruin_probability: float = 0.0
    sharpe_distribution: List[float] = field(default_factory=list)
