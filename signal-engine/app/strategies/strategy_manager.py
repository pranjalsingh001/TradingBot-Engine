"""
strategy_manager.py — Central strategy router (Phase B.6).
Routes regime -> strategy, tracks performance, handles deactivation.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from app.core.models import MarketSnapshot, Signal
from app.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class NullStrategy(BaseStrategy):
    """Returns NONE for any unclassified regime."""
    def __init__(self):
        super().__init__(strategy_id="null", target_regimes=[])
    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        return self._make_no_signal()
    def get_performance_summary(self):
        return {"strategy_id":"null","total_trades":0,"win_rate":0,"expectancy":0,"consecutive_losses":0,"is_active":True}

class StrategyManager:
    """Orchestrates strategy selection, performance tracking, deactivation."""
    def __init__(self):
        from app.strategies.trend_following import TrendFollowingStrategy
        from app.strategies.mean_reversion import MeanReversionStrategy
        from app.strategies.breakout import BreakoutStrategy
        from app.strategies.volatility_expansion import VolatilityExpansionStrategy
        self._registry = {
            "TRENDING": TrendFollowingStrategy(),
            "SIDEWAYS": MeanReversionStrategy(),
            "BREAKOUT": BreakoutStrategy(),
            "HIGH_VOLATILITY": VolatilityExpansionStrategy(),
        }
        self._null = NullStrategy()
        self._deactivation_times = {}

    def select(self, regime: str) -> BaseStrategy:
        """Return the active strategy for a regime, or NullStrategy."""
        strategy = self._registry.get(regime, self._null)
        if not strategy.is_active:
            # Check if 24h cooldown has passed
            deact_time = self._deactivation_times.get(strategy.strategy_id)
            if deact_time:
                elapsed = (datetime.now(timezone.utc) - deact_time).total_seconds()
                if elapsed > 86400:
                    strategy.activate()
                    del self._deactivation_times[strategy.strategy_id]
                    return strategy
            return self._null
        return strategy

    def update_performance(self, strategy_id: str, result: str, r_multiple: float):
        """Update performance after a trade closes. Check deactivation rules."""
        for regime, strat in self._registry.items():
            if strat.strategy_id == strategy_id:
                strat.update_performance(result, r_multiple)
                # Deactivation checks
                if strat._total_trades >= 20 and strat.win_rate < 0.35:
                    strat.deactivate(f"Win rate {strat.win_rate:.1%} < 35% over {strat._total_trades} trades")
                    self._deactivation_times[strategy_id] = datetime.now(timezone.utc)
                elif strat._total_trades >= 10:
                    avg_rr = strat._total_win_R / strat._wins if strat._wins > 0 else 0
                    if avg_rr < 0.8 and strat._wins > 0:
                        strat.deactivate(f"Avg RR {avg_rr:.2f} < 0.8")
                        self._deactivation_times[strategy_id] = datetime.now(timezone.utc)
                if strat._consecutive_losses >= 5:
                    strat.deactivate(f"5 consecutive losses")
                    self._deactivation_times[strategy_id] = datetime.now(timezone.utc)
                break

    def get_all_performance(self) -> list:
        """Return performance summaries for all strategies."""
        return [s.get_performance_summary() for s in self._registry.values()]

    def get_strategy(self, strategy_id: str) -> Optional[BaseStrategy]:
        for s in self._registry.values():
            if s.strategy_id == strategy_id:
                return s
        return None

    def get_performance_document(self, strategy_id: str) -> dict:
        """Build MongoDB document for strategy_performance collection."""
        strat = self.get_strategy(strategy_id)
        if not strat:
            return {}
        wins = strat._wins
        losses = strat._losses
        avg_rr = strat._total_win_R / wins if wins > 0 else 0
        return {
            "strategy_id": strategy_id,
            "regime": strat.target_regimes[0] if strat.target_regimes else "",
            "period_end": datetime.now(timezone.utc).isoformat(),
            "total_trades": strat._total_trades,
            "win_rate": round(strat.win_rate, 3),
            "avg_rr": round(avg_rr, 2),
            "expectancy": round(strat.expectancy, 3),
            "consecutive_losses": strat._consecutive_losses,
            "is_active": strat.is_active,
            "deactivation_reason": None if strat.is_active else "performance",
        }
