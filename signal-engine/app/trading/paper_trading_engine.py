"""
paper_trading_engine.py — Live decision + execution simulator.

Stateful engine that:
    - Processes price updates
    - Opens/closes virtual positions
    - Tracks PnL, equity, drawdown
    - Persists state to JSON for resume
    - Supports trailing stops

No real exchange connection. No real money. No randomness.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.schemas import PaperPosition, PaperTradeLog, PaperStatus

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
BUY  = "BUY"
SELL = "SELL"
OPEN   = "OPEN"
CLOSED = "CLOSED"

REASON_STOP_LOSS    = "stop_loss"
REASON_TAKE_PROFIT  = "take_profit"
REASON_MANUAL       = "manual"


# ── PaperAccount — stateful core ─────────────────────────────────────────────

class PaperAccount:
    """
    Virtual trading account with full state management.

    Tracks balance, equity, open positions, trade history,
    and persists to JSON for resumability.
    """

    def __init__(
        self,
        starting_balance: float = None,
        state_file: str = None,
    ):
        self.starting_balance = starting_balance or settings.paper_starting_balance
        self.state_file = state_file or settings.paper_state_file
        self.balance: float = self.starting_balance
        self.peak_balance: float = self.starting_balance
        self.open_positions: Dict[str, PaperPosition] = {}
        self.trade_history: List[PaperTradeLog] = []
        self.equity_curve: List[float] = [self.starting_balance]
        self.running: bool = False

    # ── Position management ──────────────────────────────────────────────────

    def has_position(self, symbol: str) -> bool:
        """Check if a position is already open for this symbol."""
        return symbol.upper() in self.open_positions

    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        position_size: float,
        stop_loss: float,
        take_profit: float,
        entry_metadata: dict = None,
    ) -> Optional[PaperPosition]:
        """
        Open a virtual position.

        Returns the Position on success, None if duplicate.
        """
        symbol = symbol.upper()

        if self.has_position(symbol):
            logger.warning("[Paper] Duplicate position blocked: %s", symbol)
            return None

        if len(self.open_positions) >= settings.max_active_trades:
            logger.warning("[Paper] Max positions reached, skipping %s", symbol)
            return None

        now = datetime.now(timezone.utc).isoformat()

        position = PaperPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=OPEN,
            unrealized_pnl=0.0,
            opened_at=now,
            entry_metadata=entry_metadata or {},
        )

        self.open_positions[symbol] = position

        logger.info(
            "[Paper] OPENED %s %s @ $%.2f | size=$%.4f | SL=$%.2f | TP=$%.2f",
            side, symbol, entry_price, position_size, stop_loss, take_profit,
        )

        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = REASON_MANUAL,
    ) -> Optional[PaperTradeLog]:
        """
        Close an open position and log the trade.

        Returns the TradeLog on success, None if no position.
        """
        symbol = symbol.upper()

        if symbol not in self.open_positions:
            return None

        pos = self.open_positions[symbol]
        now = datetime.now(timezone.utc).isoformat()

        # PnL calculation
        profit = compute_pnl(
            pos.side, pos.entry_price, exit_price, pos.position_size,
        )
        return_pct = compute_return_pct(pos.entry_price, exit_price, pos.side)

        # Update balance
        self.balance = round(self.balance + profit, 4)
        self.peak_balance = max(self.peak_balance, self.balance)

        # Log trade
        trade_log = PaperTradeLog(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            position_size=pos.position_size,
            profit=round(profit, 4),
            return_pct=round(return_pct, 4),
            reason=reason,
            opened_at=pos.opened_at,
            closed_at=now,
            entry_metadata=pos.entry_metadata,
        )

        self.trade_history.append(trade_log)
        del self.open_positions[symbol]

        logger.info(
            "[Paper] CLOSED %s %s @ $%.2f | profit=$%.2f (%.2f%%) | reason=%s",
            pos.side, symbol, exit_price, profit, return_pct, reason,
        )

        return trade_log

    # ── Price updates & exit checks ──────────────────────────────────────────

    def update_positions(
        self, prices: Dict[str, float],
    ) -> List[PaperTradeLog]:
        """
        Update all open positions with latest prices.

        Checks stop loss, take profit, and trailing stops.
        Returns list of trades that were closed.
        """
        closed_trades: List[PaperTradeLog] = []
        symbols_to_check = list(self.open_positions.keys())

        for symbol in symbols_to_check:
            if symbol not in prices:
                continue

            current_price = prices[symbol]
            pos = self.open_positions[symbol]

            # Update unrealized PnL
            pos.unrealized_pnl = round(
                compute_pnl(pos.side, pos.entry_price, current_price, pos.position_size),
                4,
            )

            # Trailing stop logic
            if settings.paper_trailing_stops:
                new_stop = compute_trailing_stop(
                    pos.side, pos.entry_price, current_price,
                    pos.stop_loss, pos.take_profit,
                )
                if new_stop != pos.stop_loss:
                    logger.info(
                        "[Paper] Trailing stop updated %s: $%.2f -> $%.2f",
                        symbol, pos.stop_loss, new_stop,
                    )
                    pos.stop_loss = new_stop

            # Check exit conditions
            exit_reason = check_exit_conditions(
                pos.side, current_price, pos.stop_loss, pos.take_profit,
            )

            if exit_reason:
                trade = self.close_position(symbol, current_price, exit_reason)
                if trade:
                    closed_trades.append(trade)

        # Update equity curve
        self._update_equity()

        return closed_trades

    # ── Equity & metrics ─────────────────────────────────────────────────────

    def _update_equity(self):
        """Recalculate equity = balance + unrealized PnL."""
        unrealized = sum(p.unrealized_pnl for p in self.open_positions.values())
        equity = round(self.balance + unrealized, 4)
        self.equity_curve.append(equity)
        self.peak_balance = max(self.peak_balance, equity)

    @property
    def equity(self) -> float:
        unrealized = sum(p.unrealized_pnl for p in self.open_positions.values())
        return round(self.balance + unrealized, 4)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return round(
            ((self.peak_balance - self.equity) / self.peak_balance) * 100, 4
        )

    @property
    def win_rate(self) -> float:
        if not self.trade_history:
            return 0.0
        winners = sum(1 for t in self.trade_history if t.profit > 0)
        return round(winners / len(self.trade_history), 4)

    @property
    def total_return_pct(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return round(
            ((self.balance - self.starting_balance) / self.starting_balance) * 100, 4
        )

    def get_status(self) -> PaperStatus:
        """Get current account snapshot."""
        return PaperStatus(
            running=self.running,
            balance=self.balance,
            equity=self.equity,
            peak_balance=self.peak_balance,
            open_positions=list(self.open_positions.values()),
            total_trades=len(self.trade_history),
            win_rate=self.win_rate,
            total_return_pct=self.total_return_pct,
            max_drawdown_pct=self.drawdown_pct,
        )

    # ── State persistence ────────────────────────────────────────────────────

    def save_state(self, path: str = None):
        """Persist account state to JSON file."""
        path = path or self.state_file
        state = {
            "starting_balance": self.starting_balance,
            "balance": self.balance,
            "peak_balance": self.peak_balance,
            "open_positions": {
                k: v.model_dump() for k, v in self.open_positions.items()
            },
            "trade_history": [t.model_dump() for t in self.trade_history],
            "equity_curve": self.equity_curve,
            "running": self.running,
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        logger.info("[Paper] State saved to %s", path)

    def load_state(self, path: str = None) -> bool:
        """
        Load account state from JSON file.

        Returns True if state was loaded, False if file not found.
        """
        path = path or self.state_file
        if not os.path.exists(path):
            logger.info("[Paper] No state file found, starting fresh")
            return False

        with open(path, "r") as f:
            state = json.load(f)

        self.starting_balance = state.get("starting_balance", self.starting_balance)
        self.balance = state.get("balance", self.starting_balance)
        self.peak_balance = state.get("peak_balance", self.balance)
        self.equity_curve = state.get("equity_curve", [self.starting_balance])
        self.running = state.get("running", False)

        self.open_positions = {}
        for k, v in state.get("open_positions", {}).items():
            self.open_positions[k] = PaperPosition(**v)

        self.trade_history = []
        for t in state.get("trade_history", []):
            self.trade_history.append(PaperTradeLog(**t))

        logger.info(
            "[Paper] State loaded: balance=$%.2f | %d open | %d history",
            self.balance, len(self.open_positions), len(self.trade_history),
        )
        return True

    def reset(self):
        """Reset account to starting state."""
        self.balance = self.starting_balance
        self.peak_balance = self.starting_balance
        self.open_positions = {}
        self.trade_history = []
        self.equity_curve = [self.starting_balance]
        self.running = False
        logger.info("[Paper] Account reset to $%.2f", self.starting_balance)


# ── Pure functions ───────────────────────────────────────────────────────────

def compute_pnl(
    side: str, entry_price: float, exit_price: float, position_size: float,
) -> float:
    """
    Compute profit/loss for a position.

    BUY:  pnl = (exit - entry) * position_size / entry
    SELL: pnl = (entry - exit) * position_size / entry

    position_size is in currency terms, so we convert to units first.
    """
    if entry_price <= 0:
        return 0.0

    units = position_size / entry_price

    if side == BUY:
        return round((exit_price - entry_price) * units, 4)
    elif side == SELL:
        return round((entry_price - exit_price) * units, 4)
    return 0.0


def compute_return_pct(
    entry_price: float, exit_price: float, side: str,
) -> float:
    """Compute return percentage for a trade."""
    if entry_price <= 0:
        return 0.0
    if side == BUY:
        return round(((exit_price - entry_price) / entry_price) * 100, 4)
    elif side == SELL:
        return round(((entry_price - exit_price) / entry_price) * 100, 4)
    return 0.0


def check_exit_conditions(
    side: str, current_price: float, stop_loss: float, take_profit: float,
) -> Optional[str]:
    """
    Check if a position should be exited.

    Returns reason string or None.
    """
    if side == BUY:
        if stop_loss > 0 and current_price <= stop_loss:
            return REASON_STOP_LOSS
        if take_profit > 0 and current_price >= take_profit:
            return REASON_TAKE_PROFIT
    elif side == SELL:
        if stop_loss > 0 and current_price >= stop_loss:
            return REASON_STOP_LOSS
        if take_profit > 0 and current_price <= take_profit:
            return REASON_TAKE_PROFIT
    return None


def compute_trailing_stop(
    side: str,
    entry_price: float,
    current_price: float,
    current_stop: float,
    take_profit: float,
) -> float:
    """
    Compute trailing stop adjustments.

    At +1R profit -> move stop to entry (breakeven)
    At +2R profit -> trail stop to lock +1R

    Only moves stop in favorable direction (never loosens).
    """
    if entry_price <= 0 or current_stop <= 0:
        return current_stop

    # Compute 1R distance
    stop_distance = abs(entry_price - current_stop)
    if stop_distance <= 0:
        return current_stop

    if side == BUY:
        profit_distance = current_price - entry_price

        # At +1R → breakeven
        if profit_distance >= stop_distance:
            new_stop = max(current_stop, entry_price)

            # At +2R → lock 1R
            if profit_distance >= stop_distance * 2:
                new_stop = max(new_stop, entry_price + stop_distance)

            return round(new_stop, 4)

    elif side == SELL:
        profit_distance = entry_price - current_price

        # At +1R → breakeven
        if profit_distance >= stop_distance:
            new_stop = min(current_stop, entry_price)

            # At +2R → lock 1R
            if profit_distance >= stop_distance * 2:
                new_stop = min(new_stop, entry_price - stop_distance)

            return round(new_stop, 4)

    return current_stop
