"""
system_runner.py — System Orchestrator.

Responsibilities:
- Initializes all components (PaperAccount, TradingLoop)
- Manages lifecycle
- Exposes unified interface for API / Dashboard
"""

from typing import Dict, Any

from app.trading.paper_trading_engine import PaperAccount
from app.trading.trading_loop import TradingLoop

class TradingSystem:
    def __init__(self):
        self.paper_account = PaperAccount()
        self.loop = TradingLoop(self.paper_account)
        self.adaptive_learning_enabled = True

    async def start(self):
        """Starts the background trading loop."""
        await self.loop.start()

    async def stop(self):
        """Stops the background trading loop safely."""
        await self.loop.stop()

    def reset(self):
        """Reset the paper account state."""
        self.paper_account.reset()

    def get_dashboard(self) -> Dict[str, Any]:
        """
        Returns a comprehensive state of the trading system,
        combining account status, recent signals, and history.
        """
        status = self.paper_account.get_status().model_dump()
        return {
            "account": {
                "balance": status["balance"],
                "equity": status["equity"],
                "drawdown": status["max_drawdown_pct"],
                "peak_balance": status["peak_balance"],
                "win_rate": status["win_rate"],
                "total_return_pct": status["total_return_pct"]
            },
            "positions": status["open_positions"],
            # Return last 10 closed trades, newest first
            "recent_trades": [t.model_dump() for t in reversed(self.paper_account.trade_history[-10:])],
            "signals": self.loop.recent_signals,
            "running": self.loop.running
        }
