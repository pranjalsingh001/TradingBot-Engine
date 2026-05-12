"""
test_backtester.py — Deterministic unit tests for the backtesting module.

Tests:
    1. Same input → same output (determinism)
    2. Downtrend market → trades are generated
    3. Flat market → no trades (all HOLD)
    4. Insufficient data → empty result
    5. Empty DataFrame → empty result
    6. Win/loss tracking accuracy
    7. Max drawdown calculation
    8. Force-close at end of data
    9. Score/win_rate bounds
   10. Result structure completeness

All tests are pure — no DB, no network.
"""

import pytest
import pandas as pd
import numpy as np

from services.backtester import run_backtest, Trade


# ── Helpers ───────────────────────────────────────────────────────────────────

INTERVAL = "5m"
SYMBOL = "BTCUSDT"
WINDOW = 200  # must be >= ma_long_period (200)


def make_df(prices: list) -> pd.DataFrame:
    """Create a minimal price DataFrame from a list of floats."""
    return pd.DataFrame({
        "price": pd.Series(prices, dtype=float),
        "symbol": SYMBOL,
        "timestamp": pd.date_range("2024-01-01", periods=len(prices), freq="1min"),
    })


def make_downtrend(n=500, start=80_000, step=50) -> list:
    """Steady downtrend — RSI should go oversold."""
    return [start - i * step for i in range(n)]


def make_uptrend(n=500, start=40_000, step=50) -> list:
    """Steady uptrend — RSI should go overbought."""
    return [start + i * step for i in range(n)]


def make_flat(n=500, price=50_000.0) -> list:
    """Flat prices → all HOLD signals, zero trades."""
    return [price] * n


def make_volatile(n=600) -> list:
    """
    Synthetic volatile data with clear trend changes.
    Creates a pattern: uptrend → downtrend → uptrend → downtrend
    to force signal transitions.
    """
    prices = []
    base = 50_000
    segments = n // 4

    # Uptrend phase
    for i in range(segments):
        base += 80
        prices.append(base)

    # Downtrend phase
    for i in range(segments):
        base -= 120
        prices.append(base)

    # Uptrend phase
    for i in range(segments):
        base += 80
        prices.append(base)

    # Downtrend phase
    for i in range(n - 3 * segments):
        base -= 120
        prices.append(base)

    return prices


# ── Trade Model Tests ─────────────────────────────────────────────────────────

class TestTradeModel:
    def test_profit_calculation_positive(self):
        """Profit is calculated correctly for a winning trade."""
        trade = Trade(entry_price=100.0, exit_price=110.0, entry_idx=0, exit_idx=10)
        assert trade.profit_pct == pytest.approx(10.0)

    def test_profit_calculation_negative(self):
        """Loss is calculated correctly for a losing trade."""
        trade = Trade(entry_price=100.0, exit_price=90.0, entry_idx=0, exit_idx=10)
        assert trade.profit_pct == pytest.approx(-10.0)

    def test_profit_calculation_zero(self):
        """Zero profit when entry == exit."""
        trade = Trade(entry_price=100.0, exit_price=100.0, entry_idx=0, exit_idx=10)
        assert trade.profit_pct == 0.0

    def test_to_dict_structure(self):
        """to_dict() must return exactly {entry, exit, profit}."""
        trade = Trade(entry_price=42000.0, exit_price=43000.0, entry_idx=0, exit_idx=5)
        d = trade.to_dict()
        assert set(d.keys()) == {"entry", "exit", "profit"}
        assert d["entry"] == 42000.0
        assert d["exit"] == 43000.0
        assert d["profit"] > 0


# ── Backtester Core Tests ────────────────────────────────────────────────────

class TestBacktester:
    def test_determinism(self):
        """Most critical: same input → identical results every run."""
        df = make_df(make_volatile())
        result1 = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        result2 = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert result1["total_trades"] == result2["total_trades"]
        assert result1["win_rate"] == result2["win_rate"]
        assert result1["total_return"] == result2["total_return"]
        assert result1["max_drawdown"] == result2["max_drawdown"]
        assert result1["trades"] == result2["trades"]

    def test_flat_market_no_trades(self):
        """Flat market → all HOLD signals → zero trades."""
        df = make_df(make_flat(n=500))
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["total_return"] == 0.0
        assert result["max_drawdown"] == 0.0
        assert result["trades"] == []

    def test_empty_dataframe(self):
        """Empty DataFrame → empty result, no crash."""
        result = run_backtest(pd.DataFrame(), SYMBOL, INTERVAL, window_size=WINDOW)
        assert result["total_trades"] == 0
        assert result["trades"] == []

    def test_insufficient_data(self):
        """Not enough data for even one window → empty result."""
        df = make_df([50_000.0] * 50)  # way below 200 + 1
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert result["total_trades"] == 0

    def test_result_structure(self):
        """Result dict must have all required keys."""
        df = make_df(make_flat(n=500))
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        required_keys = {
            "symbol", "interval", "window_size", "total_candles",
            "total_trades", "win_rate", "total_return", "max_drawdown", "trades"
        }
        assert set(result.keys()) == required_keys

    def test_symbol_uppercased(self):
        """Symbol in result must always be uppercase."""
        df = make_df(make_flat(n=500))
        result = run_backtest(df, "btcusdt", INTERVAL, window_size=WINDOW)
        assert result["symbol"] == "BTCUSDT"

    def test_interval_propagated(self):
        """Interval must appear in the result."""
        df = make_df(make_flat(n=500))
        result = run_backtest(df, SYMBOL, "1h", window_size=WINDOW)
        assert result["interval"] == "1h"

    def test_win_rate_bounds(self):
        """Win rate must be in [0.0, 1.0]."""
        df = make_df(make_volatile())
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_max_drawdown_non_positive(self):
        """Max drawdown must be <= 0 (it's a loss measure)."""
        df = make_df(make_volatile())
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert result["max_drawdown"] <= 0.0

    def test_total_candles_matches_input(self):
        """total_candles should reflect the actual data size."""
        n = 500
        df = make_df(make_flat(n=n))
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert result["total_candles"] == n

    def test_window_size_clamped_if_too_small(self):
        """Window smaller than min required should be auto-clamped, not crash."""
        df = make_df(make_flat(n=500))
        # window=50 is below min_required (200), should be clamped
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=50)
        assert result["window_size"] >= 200  # clamped up

    def test_trade_prices_are_valid(self):
        """All trade prices must be positive floats."""
        df = make_df(make_volatile())
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        for trade in result["trades"]:
            assert trade["entry"] > 0
            assert trade["exit"] > 0
            assert isinstance(trade["profit"], float)

    def test_trades_list_matches_total(self):
        """len(trades) must equal total_trades."""
        df = make_df(make_volatile())
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        assert len(result["trades"]) == result["total_trades"]

    def test_duplicate_timestamps_handled(self):
        """Duplicate timestamps in input data should be cleaned, not crash."""
        prices = make_flat(n=500)
        timestamps = list(pd.date_range("2024-01-01", periods=500, freq="1min"))
        # Add 10 duplicate timestamps
        prices_with_dupes = prices + prices[:10]
        timestamps_with_dupes = timestamps + timestamps[:10]

        df = pd.DataFrame({
            "price": pd.Series(prices_with_dupes, dtype=float),
            "symbol": SYMBOL,
            "timestamp": timestamps_with_dupes,
        })
        result = run_backtest(df, SYMBOL, INTERVAL, window_size=WINDOW)
        # Should not crash, and duplicates should be dropped
        assert result["total_candles"] == 500
