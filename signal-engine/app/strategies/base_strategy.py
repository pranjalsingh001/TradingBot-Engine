"""
base_strategy.py — Abstract base class for all strategy archetypes (Phase B).

Every strategy must inherit from BaseStrategy and implement evaluate()
and get_performance_summary(). The Signal dataclass is the contract
between strategies and the risk engine.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import dataclass, field

from app.core.models import MarketSnapshot, Signal

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Abstract base for all regime-specific strategy archetypes."""

    strategy_id: str = "base"
    target_regimes: list = field(default_factory=list)
    is_active: bool = True

    # Performance tracking
    _total_trades: int = 0
    _wins: int = 0
    _losses: int = 0
    _consecutive_losses: int = 0
    _total_rr: float = 0.0
    _total_win_R: float = 0.0
    _total_loss_R: float = 0.0

    def __init__(self, strategy_id: str, target_regimes: list):
        self.strategy_id = strategy_id
        self.target_regimes = target_regimes
        self.is_active = True
        self._total_trades = 0
        self._wins = 0
        self._losses = 0
        self._consecutive_losses = 0
        self._total_rr = 0.0
        self._total_win_R = 0.0
        self._total_loss_R = 0.0

    @abstractmethod
    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """
        Core signal logic. Must return a Signal dataclass.
        Returns Signal(direction="NONE") if no valid setup found.
        """
        ...

    @abstractmethod
    def get_performance_summary(self) -> dict:
        """Returns win_rate, expectancy, avg_rr, trade_count."""
        ...

    def update_performance(self, result: str, r_multiple: float):
        """Update performance tracking after a trade closes."""
        self._total_trades += 1
        if result == "WIN":
            self._wins += 1
            self._consecutive_losses = 0
            self._total_win_R += r_multiple
        elif result == "LOSS":
            self._losses += 1
            self._consecutive_losses += 1
            self._total_loss_R += abs(r_multiple)

    def deactivate(self, reason: str):
        """Deactivate the strategy with a reason."""
        self.is_active = False
        logger.warning("[Strategy] %s deactivated: %s", self.strategy_id, reason)

    def activate(self):
        """Reactivate the strategy."""
        self.is_active = True
        logger.info("[Strategy] %s reactivated", self.strategy_id)

    def _make_no_signal(self) -> Signal:
        """Helper to create a NONE signal."""
        return Signal(
            direction="NONE",
            confidence=0.0,
            entry_price=0.0,
            raw_sl=0.0,
            raw_tp=0.0,
            strategy_id=self.strategy_id,
            regime="",
            timestamp=datetime.utcnow(),
        )

    @property
    def win_rate(self) -> float:
        if self._total_trades == 0:
            return 0.0
        return self._wins / self._total_trades

    @property
    def expectancy(self) -> float:
        if self._total_trades == 0:
            return 0.0
        avg_win_r = self._total_win_R / self._wins if self._wins > 0 else 0.0
        avg_loss_r = self._total_loss_R / self._losses if self._losses > 0 else 0.0
        return (self.win_rate * avg_win_r) - ((1 - self.win_rate) * avg_loss_r)
