"""
strategies/__init__.py — Strategy Archetype System (Phase B).
"""
from app.strategies.base_strategy import BaseStrategy, Signal
from app.strategies.strategy_manager import StrategyManager

__all__ = ["BaseStrategy", "Signal", "StrategyManager"]
