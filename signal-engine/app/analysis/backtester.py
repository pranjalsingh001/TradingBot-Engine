"""
backtester.py — Deterministic backtesting engine.

Iterates over historical price data with a rolling window,
calls the existing signal engine at each step, and simulates trades.

Single responsibility: backtest simulation only.
No DB calls. No HTTP. No randomness.
Reuses generate_signal() without modification.
"""

import logging
from typing import List, Optional

import pandas as pd

from app.core.config import settings
from app.engines.signal_engine import generate_signal, BUY, SELL, HOLD
from app.core.schemas import SignalResponse, ErrorResponse

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────

class Trade:
    """Represents a single completed trade (entry → exit)."""
    __slots__ = ("entry_price", "exit_price", "entry_idx", "exit_idx", "profit_pct")

    def __init__(self, entry_price: float, exit_price: float,
                 entry_idx: int, exit_idx: int):
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.entry_idx = entry_idx
        self.exit_idx = exit_idx
        self.profit_pct = round(((exit_price - entry_price) / entry_price) * 100, 4)

    def to_dict(self) -> dict:
        return {
            "entry": self.entry_price,
            "exit": self.exit_price,
            "profit": self.profit_pct,
        }


# ── Core backtester ───────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    window_size: int = 200,
) -> dict:
    """
    Run a deterministic backtest over a price DataFrame.

    Parameters
    ----------
    df          : pd.DataFrame  Full historical data, ASC sorted by timestamp.
                                Must have columns: [price, timestamp]
    symbol      : str           e.g. "BTCUSDT"
    interval    : str           e.g. "5m", "1h"
    window_size : int           Rolling window size passed to signal engine.
                                Must be >= ma_long_period (200) for MA200 to compute.

    Returns
    -------
    dict with keys:
        total_trades, win_rate, total_return, max_drawdown, trades
    """
    symbol = symbol.upper()

    # ── Validate inputs ───────────────────────────────────────────────────────
    min_window = max(settings.rsi_period + 1, settings.ma_long_period)
    if window_size < min_window:
        window_size = min_window
        logger.warning(
            "[Backtest] window_size too small, clamped to %d", window_size
        )

    if df.empty or len(df) < window_size + 1:
        logger.warning(
            "[Backtest] Insufficient data: need >%d rows, got %d",
            window_size, len(df) if not df.empty else 0,
        )
        return _empty_result()

    # Ensure clean data
    df = df.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df.dropna(subset=["price"], inplace=True)
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.sort_values("timestamp", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)

    if len(df) < window_size + 1:
        return _empty_result()

    # ── Simulation state ──────────────────────────────────────────────────────
    trades: List[Trade] = []
    in_position = False
    entry_price: Optional[float] = None
    entry_idx: Optional[int] = None

    # Track equity curve for drawdown calculation
    cumulative_return = 0.0
    peak_return = 0.0
    max_drawdown = 0.0

    # ── Rolling window iteration ──────────────────────────────────────────────
    total_steps = len(df) - window_size
    logger.info(
        "[Backtest] Starting: symbol=%s interval=%s window=%d steps=%d",
        symbol, interval, window_size, total_steps,
    )

    for i in range(total_steps):
        window_df = df.iloc[i : i + window_size].copy().reset_index(drop=True)
        current_price = float(window_df["price"].iloc[-1])

        # Call the existing signal engine — no modification
        result = generate_signal(window_df, symbol, interval)

        # Skip if signal engine returned an error
        if isinstance(result, ErrorResponse):
            continue

        signal = result.signal

        # ── Trading rules ─────────────────────────────────────────────────────
        if signal == BUY and not in_position:
            # Open position
            in_position = True
            entry_price = current_price
            entry_idx = i + window_size - 1  # index in the original df

        elif signal == SELL and in_position:
            # Close position
            trade = Trade(
                entry_price=entry_price,
                exit_price=current_price,
                entry_idx=entry_idx,
                exit_idx=i + window_size - 1,
            )
            trades.append(trade)

            # Update equity tracking
            cumulative_return += trade.profit_pct
            peak_return = max(peak_return, cumulative_return)
            drawdown = cumulative_return - peak_return
            max_drawdown = min(max_drawdown, drawdown)

            in_position = False
            entry_price = None
            entry_idx = None

        # HOLD → do nothing

    # ── If still in position at end, force-close at last price ────────────────
    if in_position and entry_price is not None:
        last_price = float(df["price"].iloc[-1])
        trade = Trade(
            entry_price=entry_price,
            exit_price=last_price,
            entry_idx=entry_idx,
            exit_idx=len(df) - 1,
        )
        trades.append(trade)
        cumulative_return += trade.profit_pct
        peak_return = max(peak_return, cumulative_return)
        drawdown = cumulative_return - peak_return
        max_drawdown = min(max_drawdown, drawdown)

    # ── Build result ──────────────────────────────────────────────────────────
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t.profit_pct > 0)
    win_rate = round(winning_trades / total_trades, 4) if total_trades > 0 else 0.0

    result = {
        "symbol": symbol,
        "interval": interval,
        "window_size": window_size,
        "total_candles": len(df),
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_return": round(cumulative_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "trades": [t.to_dict() for t in trades],
    }

    logger.info(
        "[Backtest] Complete: trades=%d win_rate=%.2f return=%.2f%% drawdown=%.2f%%",
        total_trades, win_rate, cumulative_return, max_drawdown,
    )

    return result


def _empty_result() -> dict:
    """Return a zero-valued backtest result for insufficient data."""
    return {
        "symbol": "",
        "interval": "",
        "window_size": 0,
        "total_candles": 0,
        "total_trades": 0,
        "win_rate": 0.0,
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "trades": [],
    }
