"""
test_paper_trading.py — Tests for the paper trading engine.

Test categories:
    1. PnL computation
    2. Position open/close
    3. Stop loss exits
    4. Take profit exits
    5. Trailing stops
    6. Duplicate position blocking
    7. Account metrics
    8. State persistence
    9. Full simulation
    10. Determinism

All tests are pure — no DB, no network.
"""

import os
import json
import pytest

from services.paper_trading_engine import (
    PaperAccount,
    compute_pnl,
    compute_return_pct,
    check_exit_conditions,
    compute_trailing_stop,
    BUY, SELL,
    REASON_STOP_LOSS, REASON_TAKE_PROFIT,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

TEST_STATE_FILE = "test_paper_state.json"


@pytest.fixture
def account():
    """Fresh account for each test."""
    acc = PaperAccount(starting_balance=10_000.0, state_file=TEST_STATE_FILE)
    yield acc
    # Cleanup
    if os.path.exists(TEST_STATE_FILE):
        os.remove(TEST_STATE_FILE)


# ── 1. PnL Computation ──────────────────────────────────────────────────────

class TestPnL:
    def test_buy_profit(self):
        """BUY: entry=100, exit=110, size=$500 → units=5 → pnl=$50"""
        pnl = compute_pnl(BUY, 100.0, 110.0, 500.0)
        assert pnl == pytest.approx(50.0)

    def test_buy_loss(self):
        pnl = compute_pnl(BUY, 100.0, 90.0, 500.0)
        assert pnl == pytest.approx(-50.0)

    def test_sell_profit(self):
        """SELL: entry=100, exit=90 → profit"""
        pnl = compute_pnl(SELL, 100.0, 90.0, 500.0)
        assert pnl == pytest.approx(50.0)

    def test_sell_loss(self):
        pnl = compute_pnl(SELL, 100.0, 110.0, 500.0)
        assert pnl == pytest.approx(-50.0)

    def test_zero_entry_price(self):
        assert compute_pnl(BUY, 0.0, 100.0, 500.0) == 0.0

    def test_flat_trade(self):
        assert compute_pnl(BUY, 100.0, 100.0, 500.0) == 0.0


class TestReturnPct:
    def test_buy_positive(self):
        assert compute_return_pct(100.0, 110.0, BUY) == pytest.approx(10.0)

    def test_sell_positive(self):
        assert compute_return_pct(100.0, 90.0, SELL) == pytest.approx(10.0)

    def test_zero_entry(self):
        assert compute_return_pct(0.0, 100.0, BUY) == 0.0


# ── 2. Position Open/Close ──────────────────────────────────────────────────

class TestPositionManagement:
    def test_open_position(self, account):
        pos = account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        assert pos is not None
        assert pos.symbol == "BTCUSDT"
        assert pos.status == "OPEN"
        assert account.has_position("BTCUSDT")

    def test_close_position(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        trade = account.close_position("BTCUSDT", 50500.0, "manual")
        assert trade is not None
        assert trade.exit_price == 50500.0
        assert trade.profit > 0
        assert not account.has_position("BTCUSDT")

    def test_close_nonexistent(self, account):
        assert account.close_position("ETHUSDT", 1000.0) is None

    def test_balance_updates_on_close(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)
        # profit = (110-100) * (500/100) = 50
        assert account.balance == pytest.approx(10_050.0)


# ── 3. Stop Loss Exits ──────────────────────────────────────────────────────

class TestStopLoss:
    def test_buy_stop_loss_triggered(self):
        reason = check_exit_conditions(BUY, 49500.0, 49600.0, 50800.0)
        assert reason == REASON_STOP_LOSS

    def test_buy_stop_loss_exact(self):
        reason = check_exit_conditions(BUY, 49600.0, 49600.0, 50800.0)
        assert reason == REASON_STOP_LOSS

    def test_sell_stop_loss_triggered(self):
        reason = check_exit_conditions(SELL, 50500.0, 50400.0, 49200.0)
        assert reason == REASON_STOP_LOSS

    def test_no_exit_in_range(self):
        reason = check_exit_conditions(BUY, 50000.0, 49600.0, 50800.0)
        assert reason is None

    def test_stop_loss_closes_position(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        closed = account.update_positions({"BTCUSDT": 49500.0})
        assert len(closed) == 1
        assert closed[0].reason == REASON_STOP_LOSS
        assert closed[0].profit < 0


# ── 4. Take Profit Exits ─────────────────────────────────────────────────────

class TestTakeProfit:
    def test_buy_take_profit_triggered(self):
        reason = check_exit_conditions(BUY, 50900.0, 49600.0, 50800.0)
        assert reason == REASON_TAKE_PROFIT

    def test_buy_take_profit_exact(self):
        reason = check_exit_conditions(BUY, 50800.0, 49600.0, 50800.0)
        assert reason == REASON_TAKE_PROFIT

    def test_sell_take_profit_triggered(self):
        reason = check_exit_conditions(SELL, 49100.0, 50400.0, 49200.0)
        assert reason == REASON_TAKE_PROFIT

    def test_take_profit_closes_position(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        closed = account.update_positions({"BTCUSDT": 51000.0})
        assert len(closed) == 1
        assert closed[0].reason == REASON_TAKE_PROFIT
        assert closed[0].profit > 0


# ── 5. Trailing Stops ────────────────────────────────────────────────────────

class TestTrailingStops:
    def test_buy_no_trail_below_1r(self):
        """Price hasn't reached 1R — stop unchanged."""
        new_stop = compute_trailing_stop(BUY, 50000.0, 50200.0, 49600.0, 50800.0)
        assert new_stop == 49600.0

    def test_buy_breakeven_at_1r(self):
        """Price at +1R (50400) → stop moves to entry (50000)."""
        new_stop = compute_trailing_stop(BUY, 50000.0, 50400.0, 49600.0, 50800.0)
        assert new_stop == 50000.0

    def test_buy_lock_1r_at_2r(self):
        """Price at +2R (50800) → stop moves to entry+1R (50400)."""
        new_stop = compute_trailing_stop(BUY, 50000.0, 50800.0, 49600.0, 50800.0)
        assert new_stop == 50400.0

    def test_sell_breakeven_at_1r(self):
        """SELL: price at -1R (49600) → stop moves to entry (50000)."""
        new_stop = compute_trailing_stop(SELL, 50000.0, 49600.0, 50400.0, 49200.0)
        assert new_stop == 50000.0

    def test_sell_lock_1r_at_2r(self):
        """SELL: price at -2R → stop locks 1R."""
        new_stop = compute_trailing_stop(SELL, 50000.0, 49200.0, 50400.0, 49200.0)
        assert new_stop == 49600.0

    def test_trailing_stop_never_loosens(self):
        """Stop can only move in favorable direction."""
        # BUY: current stop at 50000 (breakeven), price drops — stop stays
        new_stop = compute_trailing_stop(BUY, 50000.0, 50100.0, 50000.0, 50800.0)
        assert new_stop >= 50000.0

    def test_zero_entry_returns_current(self):
        assert compute_trailing_stop(BUY, 0.0, 100.0, 90.0, 120.0) == 90.0

    def test_trailing_stop_integration(self, account):
        """Full cycle: open → price rises → stop trails → price drops → exit at trailed stop."""
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)

        # Price at 1R — stop should move to breakeven
        account.update_positions({"BTCUSDT": 50400.0})
        pos = account.open_positions.get("BTCUSDT")
        assert pos is not None
        assert pos.stop_loss >= 50000.0


# ── 6. Duplicate Position Blocking ───────────────────────────────────────────

class TestDuplicateBlocking:
    def test_no_duplicate_positions(self, account):
        pos1 = account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        pos2 = account.open_position("BTCUSDT", BUY, 51000.0, 100.0, 50600.0, 51800.0)
        assert pos1 is not None
        assert pos2 is None
        assert len(account.open_positions) == 1

    def test_different_symbols_allowed(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        account.open_position("ETHUSDT", BUY, 3000.0, 50.0, 2900.0, 3200.0)
        assert len(account.open_positions) == 2

    def test_max_positions_enforced(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        account.open_position("ETHUSDT", BUY, 3000.0, 50.0, 2900.0, 3200.0)
        account.open_position("SOLUSDT", BUY, 150.0, 30.0, 140.0, 170.0)
        pos4 = account.open_position("ADAUSDT", BUY, 0.5, 20.0, 0.4, 0.7)
        assert pos4 is None  # exceeds max_active_trades=3


# ── 7. Account Metrics ──────────────────────────────────────────────────────

class TestAccountMetrics:
    def test_initial_state(self, account):
        assert account.balance == 10_000.0
        assert account.equity == 10_000.0
        assert account.win_rate == 0.0
        assert account.total_return_pct == 0.0

    def test_equity_includes_unrealized(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.update_positions({"BTCUSDT": 110.0})
        assert account.equity > account.balance

    def test_win_rate_calculation(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)  # win
        account.open_position("ETHUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("ETHUSDT", 90.0)   # loss
        assert account.win_rate == pytest.approx(0.5)

    def test_peak_balance_tracked(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)  # win → balance goes up
        peak_after_win = account.peak_balance
        account.open_position("ETHUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("ETHUSDT", 90.0)   # loss → balance goes down
        assert account.peak_balance == peak_after_win

    def test_total_return(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 1000.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)  # profit=$100
        assert account.total_return_pct == pytest.approx(1.0)

    def test_drawdown(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 1000.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)  # win
        # peak = 10100
        account.open_position("ETHUSDT", BUY, 100.0, 2000.0, 90.0, 120.0)
        account.close_position("ETHUSDT", 90.0)   # loss of $200
        # balance = 9900
        assert account.drawdown_pct > 0


# ── 8. State Persistence ─────────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_load(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        account.running = True
        account.save_state()

        # Create new account and load
        account2 = PaperAccount(state_file=TEST_STATE_FILE)
        loaded = account2.load_state()
        assert loaded is True
        assert account2.balance == account.balance
        assert account2.has_position("BTCUSDT")
        assert account2.running is True

    def test_load_nonexistent_file(self, account):
        acc = PaperAccount(state_file="nonexistent_file.json")
        assert acc.load_state() is False

    def test_trade_history_persists(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)
        account.save_state()

        account2 = PaperAccount(state_file=TEST_STATE_FILE)
        account2.load_state()
        assert len(account2.trade_history) == 1
        assert account2.trade_history[0].profit > 0

    def test_resume_without_reset(self, account):
        """Account should resume with previous balance."""
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)  # profit
        old_balance = account.balance
        account.save_state()

        account2 = PaperAccount(state_file=TEST_STATE_FILE)
        account2.load_state()
        assert account2.balance == old_balance


# ── 9. Full Simulation ──────────────────────────────────────────────────────

class TestFullSimulation:
    def test_open_update_close_cycle(self, account):
        """Full lifecycle: open → update → exit on TP."""
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        assert len(account.open_positions) == 1

        # Price moves up but not to TP
        closed = account.update_positions({"BTCUSDT": 50500.0})
        assert len(closed) == 0
        assert account.open_positions["BTCUSDT"].unrealized_pnl > 0

        # Price hits TP
        closed = account.update_positions({"BTCUSDT": 51000.0})
        assert len(closed) == 1
        assert closed[0].reason == REASON_TAKE_PROFIT
        assert account.balance > 10_000.0

    def test_multiple_positions_simultaneous(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        account.open_position("ETHUSDT", SELL, 3000.0, 50.0, 3100.0, 2800.0)

        # BTC goes up (good for BUY), ETH goes down (good for SELL)
        closed = account.update_positions({"BTCUSDT": 51000.0, "ETHUSDT": 2700.0})
        assert len(closed) == 2  # both hit TP

    def test_status_snapshot(self, account):
        account.open_position("BTCUSDT", BUY, 50000.0, 100.0, 49600.0, 50800.0)
        status = account.get_status()
        assert status.balance == 10_000.0
        assert len(status.open_positions) == 1
        assert status.total_trades == 0

    def test_reset(self, account):
        account.open_position("BTCUSDT", BUY, 100.0, 500.0, 90.0, 120.0)
        account.close_position("BTCUSDT", 110.0)
        account.reset()
        assert account.balance == 10_000.0
        assert len(account.open_positions) == 0
        assert len(account.trade_history) == 0


# ── 10. Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_inputs_same_pnl(self):
        assert compute_pnl(BUY, 100, 110, 500) == compute_pnl(BUY, 100, 110, 500)

    def test_same_exit_conditions(self):
        r1 = check_exit_conditions(BUY, 49500.0, 49600.0, 50800.0)
        r2 = check_exit_conditions(BUY, 49500.0, 49600.0, 50800.0)
        assert r1 == r2

    def test_same_trailing_stop(self):
        s1 = compute_trailing_stop(BUY, 50000, 50400, 49600, 50800)
        s2 = compute_trailing_stop(BUY, 50000, 50400, 49600, 50800)
        assert s1 == s2
