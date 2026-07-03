"""
test_evaluation_engine.py — Tests for the quantitative strategy evaluation framework.

Test categories:
    1. Total return
    2. Win rate
    3. Profit factor (including edge cases)
    4. Expectancy
    5. Max drawdown
    6. Sharpe ratio
    7. Trade distribution
    8. Consistency
    9. Interpretation / grading
    10. Full pipeline
    11. Determinism
    12. Edge cases

All tests are pure — no DB, no network.
"""

import pytest

from services.evaluation_engine import (
    compute_total_return,
    compute_win_rate,
    compute_profit_factor,
    compute_expectancy,
    compute_max_drawdown,
    compute_sharpe_ratio,
    compute_distribution,
    compute_consistency,
    compute_interpretation,
    evaluate_backtest,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trades(profits: list) -> list:
    return [{"profit": p} for p in profits]


# ── 1. Total Return ──────────────────────────────────────────────────────────

class TestTotalReturn:
    def test_positive_return(self):
        curve = [10000, 10500, 11000]
        assert compute_total_return(curve) == pytest.approx(10.0)

    def test_negative_return(self):
        curve = [10000, 9500, 9000]
        assert compute_total_return(curve) == pytest.approx(-10.0)

    def test_flat(self):
        curve = [10000, 10000, 10000]
        assert compute_total_return(curve) == 0.0

    def test_single_point(self):
        assert compute_total_return([10000]) == 0.0

    def test_empty(self):
        assert compute_total_return([]) == 0.0

    def test_zero_start(self):
        assert compute_total_return([0, 100]) == 0.0


# ── 2. Win Rate ──────────────────────────────────────────────────────────────

class TestWinRate:
    def test_all_winners(self):
        assert compute_win_rate([100, 200, 50]) == pytest.approx(1.0)

    def test_all_losers(self):
        assert compute_win_rate([-100, -200]) == 0.0

    def test_mixed(self):
        assert compute_win_rate([100, -50, 200, -30]) == pytest.approx(0.5)

    def test_empty(self):
        assert compute_win_rate([]) == 0.0

    def test_zero_profits_not_winners(self):
        assert compute_win_rate([0, 0, 100]) == pytest.approx(1 / 3, abs=0.01)


# ── 3. Profit Factor ────────────────────────────────────────────────────────

class TestProfitFactor:
    def test_basic(self):
        """$300 profit / $100 loss = 3.0"""
        pf = compute_profit_factor([100, 200, -50, -50])
        assert pf == pytest.approx(3.0)

    def test_no_losses(self):
        """All winners → 999.99 (safe infinity)."""
        assert compute_profit_factor([100, 200]) == 999.99

    def test_no_wins(self):
        """All losers → 0.0."""
        assert compute_profit_factor([-100, -200]) == 0.0

    def test_empty(self):
        assert compute_profit_factor([]) == 0.0

    def test_breakeven(self):
        """Equal profit and loss → PF = 1.0."""
        pf = compute_profit_factor([100, -100])
        assert pf == pytest.approx(1.0)

    def test_no_wins_no_losses(self):
        """All zero → 0.0."""
        assert compute_profit_factor([0, 0]) == 0.0


# ── 4. Expectancy ────────────────────────────────────────────────────────────

class TestExpectancy:
    def test_positive_expectancy(self):
        """More avg win × win_rate than avg loss × loss_rate."""
        exp = compute_expectancy([200, -50, 150, -30])
        assert exp > 0

    def test_negative_expectancy(self):
        exp = compute_expectancy([-200, 50, -150, 30])
        assert exp < 0

    def test_empty(self):
        assert compute_expectancy([]) == 0.0

    def test_all_winners(self):
        exp = compute_expectancy([100, 200, 300])
        assert exp > 0

    def test_all_losers(self):
        exp = compute_expectancy([-100, -200])
        assert exp < 0


# ── 5. Max Drawdown ──────────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_no_drawdown(self):
        """Monotonically increasing → 0% drawdown."""
        dd = compute_max_drawdown([100, 110, 120, 130])
        assert dd == 0.0

    def test_simple_drawdown(self):
        """Peak 200, trough 100 → 50% drawdown."""
        dd = compute_max_drawdown([100, 200, 100])
        assert dd == pytest.approx(50.0)

    def test_recovery_doesnt_erase_dd(self):
        """Even after recovery, max DD is remembered."""
        dd = compute_max_drawdown([100, 200, 150, 250])
        assert dd == pytest.approx(25.0)

    def test_continuous_decline(self):
        dd = compute_max_drawdown([1000, 900, 800, 700])
        assert dd == pytest.approx(30.0)

    def test_single_point(self):
        assert compute_max_drawdown([10000]) == 0.0

    def test_empty(self):
        assert compute_max_drawdown([]) == 0.0

    def test_flat_curve(self):
        assert compute_max_drawdown([100, 100, 100]) == 0.0


# ── 6. Sharpe Ratio ──────────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_positive_returns_positive_sharpe(self):
        curve = [10000 + i * 100 for i in range(50)]
        sharpe = compute_sharpe_ratio(curve)
        assert sharpe > 0

    def test_flat_curve_zero_sharpe(self):
        curve = [10000] * 50
        assert compute_sharpe_ratio(curve) == 0.0

    def test_volatile_lower_sharpe(self):
        """Volatile curve should have lower Sharpe than smooth."""
        smooth = [10000 + i * 10 for i in range(50)]
        volatile = [10000 + i * 10 + ((-1) ** i) * 500 for i in range(50)]
        sharpe_smooth = compute_sharpe_ratio(smooth)
        sharpe_volatile = compute_sharpe_ratio(volatile)
        assert sharpe_smooth > sharpe_volatile

    def test_too_few_points(self):
        assert compute_sharpe_ratio([100, 200]) == 0.0

    def test_empty(self):
        assert compute_sharpe_ratio([]) == 0.0

    def test_determinism(self):
        curve = [10000 + i * 50 for i in range(100)]
        assert compute_sharpe_ratio(curve) == compute_sharpe_ratio(curve)


# ── 7. Distribution ──────────────────────────────────────────────────────────

class TestDistribution:
    def test_avg_win(self):
        d = compute_distribution([100, 200, -50, -30])
        assert d["avg_win"] == pytest.approx(150.0)

    def test_avg_loss(self):
        d = compute_distribution([100, 200, -50, -30])
        assert d["avg_loss"] == pytest.approx(-40.0)

    def test_largest_win(self):
        d = compute_distribution([100, 500, -50])
        assert d["largest_win"] == 500.0

    def test_largest_loss(self):
        d = compute_distribution([100, -200, -50])
        assert d["largest_loss"] == -200.0

    def test_consecutive_wins(self):
        d = compute_distribution([100, 200, 300, -50, 100])
        assert d["max_consecutive_wins"] == 3

    def test_consecutive_losses(self):
        d = compute_distribution([100, -50, -30, -20, 100])
        assert d["max_consecutive_losses"] == 3

    def test_empty(self):
        d = compute_distribution([])
        assert d["avg_win"] == 0.0
        assert d["max_consecutive_wins"] == 0


# ── 8. Consistency ───────────────────────────────────────────────────────────

class TestConsistency:
    def test_distributed_profits(self):
        """10 equal winners → top 10% contributes 10%."""
        c = compute_consistency([100] * 10)
        assert c["top_10_pct_contribution"] == pytest.approx(0.1)
        assert c["is_concentrated"] is False

    def test_concentrated_profits(self):
        """1 big winner + 9 small → concentrated."""
        c = compute_consistency([1000] + [10] * 9)
        assert c["is_concentrated"] is True

    def test_empty(self):
        c = compute_consistency([])
        assert c["is_concentrated"] is False

    def test_all_losers(self):
        c = compute_consistency([-100, -200])
        assert c["top_10_pct_contribution"] == 0.0


# ── 9. Interpretation ────────────────────────────────────────────────────────

class TestInterpretation:
    def test_strong_system_high_grade(self):
        interp = compute_interpretation(
            total_return=50.0, win_rate=0.65,
            profit_factor=2.5, expectancy=150.0,
            max_drawdown=5.0, sharpe=2.5,
        )
        assert interp["grade"] in ("A", "B")
        assert any("Strong edge" in f for f in interp["flags"])

    def test_weak_system_low_grade(self):
        interp = compute_interpretation(
            total_return=-10.0, win_rate=0.3,
            profit_factor=0.8, expectancy=-50.0,
            max_drawdown=25.0, sharpe=-0.5,
        )
        assert interp["grade"] in ("D", "F")

    def test_high_drawdown_flagged(self):
        interp = compute_interpretation(
            total_return=20.0, win_rate=0.55,
            profit_factor=1.5, expectancy=50.0,
            max_drawdown=25.0, sharpe=1.2,
        )
        assert any("High risk" in f for f in interp["flags"])

    def test_low_profit_factor_flagged(self):
        interp = compute_interpretation(
            total_return=5.0, win_rate=0.5,
            profit_factor=1.1, expectancy=10.0,
            max_drawdown=8.0, sharpe=0.8,
        )
        assert any("Weak edge" in f for f in interp["flags"])


# ── 10. Full Pipeline ────────────────────────────────────────────────────────

class TestEvaluateBacktest:
    def test_basic_evaluation(self):
        trades = make_trades([100, -30, 200, -50, 150])
        curve = [10000, 10100, 10070, 10270, 10220, 10370]
        result = evaluate_backtest(trades, curve)
        assert result.summary.total_trades == 5
        assert result.summary.total_return_pct > 0
        assert result.summary.win_rate > 0
        assert result.interpretation.grade in ("A", "B", "C", "D", "F")

    def test_empty_trades(self):
        result = evaluate_backtest([], [10000])
        assert result.summary.total_trades == 0
        assert result.summary.win_rate == 0.0

    def test_all_fields_present(self):
        trades = make_trades([100, -50, 200])
        curve = [10000, 10100, 10050, 10250]
        result = evaluate_backtest(trades, curve)
        assert hasattr(result, "summary")
        assert hasattr(result, "distribution")
        assert hasattr(result, "consistency")
        assert hasattr(result, "interpretation")

    def test_determinism(self):
        trades = make_trades([100, -30, 200, -50])
        curve = [10000, 10100, 10070, 10270, 10220]
        r1 = evaluate_backtest(trades, curve)
        r2 = evaluate_backtest(trades, curve)
        assert r1.summary.total_return_pct == r2.summary.total_return_pct
        assert r1.summary.sharpe_ratio == r2.summary.sharpe_ratio
        assert r1.summary.max_drawdown_pct == r2.summary.max_drawdown_pct
        assert r1.interpretation.grade == r2.interpretation.grade

    def test_losing_system(self):
        trades = make_trades([-100, -200, -50, 30])
        curve = [10000, 9900, 9700, 9650, 9680]
        result = evaluate_backtest(trades, curve)
        assert result.summary.total_return_pct < 0
        assert result.summary.expectancy < 0
        assert result.summary.profit_factor < 1.0

    def test_perfect_system(self):
        trades = make_trades([100, 200, 300, 400, 500])
        curve = [10000, 10100, 10300, 10600, 11000, 11500]
        result = evaluate_backtest(trades, curve)
        assert result.summary.win_rate == 1.0
        assert result.summary.profit_factor == 999.99
        assert result.summary.expectancy > 0
        assert result.interpretation.grade in ("A", "B")
