"""
global_risk_controls.py — Circuit breakers and global risk limits (Phase C.3).
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from app.core.models import Signal, MarketSnapshot, PortfolioState, SizedSignal
from app.risk.atr_risk import compute_sl_tp
from app.risk.position_sizer import compute_position_size

logger = logging.getLogger(__name__)

class GlobalRiskControls:
    def __init__(self, max_daily_dd_pct=3.0, max_consec_losses=4):
        self.max_daily_dd_pct = max_daily_dd_pct
        self.max_consec_losses = max_consec_losses
        self._size_reduction = 1.0
        self._trades_at_reduced = 0

    def is_paused(self, portfolio: PortfolioState) -> tuple:
        """Check all circuit breakers. Returns (paused: bool, reason: str)."""
        # Daily drawdown limit
        if portfolio.daily_drawdown_pct >= self.max_daily_dd_pct:
            return True, "Daily drawdown limit hit"
        # Emergency: 2x daily drawdown
        if portfolio.daily_drawdown_pct >= self.max_daily_dd_pct * 2:
            return True, "Emergency: runaway loss day"
        # Manual pause
        if portfolio.is_paused:
            return True, portfolio.pause_reason
        return False, ""

    def get_size_modifier(self, portfolio: PortfolioState, regime: str) -> float:
        """Return position size multiplier based on risk state."""
        modifier = 1.0
        # Consecutive loss reduction
        if portfolio.consecutive_losses >= self.max_consec_losses:
            modifier *= 0.5
            self._trades_at_reduced += 1
            if self._trades_at_reduced > 10:
                self._trades_at_reduced = 0
        # HIGH_VOLATILITY 50% reduction
        if regime == "HIGH_VOLATILITY":
            modifier *= 0.5
        # Regime instability (changed in last 2 periods)
        if len(portfolio.recent_regimes) >= 3:
            if len(set(portfolio.recent_regimes[-3:])) > 1:
                modifier *= 0.75
        return modifier


def apply_risk(
    signal: Signal,
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
    risk_controls: Optional[GlobalRiskControls] = None,
) -> Optional[SizedSignal]:
    """
    Main risk engine entry point (Phase C.4).
    Returns None if trade blocked, SizedSignal if allowed.
    """
    if risk_controls is None:
        risk_controls = GlobalRiskControls()

    if signal.direction == "NONE":
        return None

    paused, reason = risk_controls.is_paused(portfolio)
    if paused:
        logger.warning("[Risk] Trading paused: %s", reason)
        return None

    sl, tp = compute_sl_tp(signal, snapshot.atr_5m, snapshot.regime)
    qty, dollar_risk = compute_position_size(signal, sl, snapshot, portfolio)

    if qty <= 0:
        return None

    # Apply size modifier
    modifier = risk_controls.get_size_modifier(portfolio, snapshot.regime)
    qty = round(qty * modifier, 6)
    dollar_risk = round(dollar_risk * modifier, 2)

    return SizedSignal(
        signal=signal, sl=sl, tp=tp,
        quantity=qty, dollar_risk=dollar_risk,
        regime=snapshot.regime,
    )
