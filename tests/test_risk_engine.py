"""
test_risk_engine.py — Tests for the risk-controlled trading engine.

Test categories:
    1. Risk filters (signal, confidence, volatility, trades, drawdown, exposure, correlation)
    2. Position sizing (risk-based: large stop → small position, small stop → large position)
    3. Risk consistency (actual risk ≤ risk_amount)
    4. Stop loss / take profit
    5. Trailing stops
    6. Portfolio exposure
    7. Full pipeline integration
    8. Determinism

All tests are pure — no DB, no network.
"""

import pytest

from services.risk_engine import (
    check_signal_actionable,
    check_confidence,
    check_volatility,
    check_active_trades,
    check_drawdown,
    check_portfolio_exposure,
    check_correlation,
    compute_position_size,
    compute_position_units,
    compute_stop_loss,
    compute_take_profit,
    compute_stop_loss_distance,
    compute_trailing_stops,
    validate_risk_consistency,
    evaluate_risk,
)
from services.schemas import (
    SignalResponse, IndicatorValues, FactorBreakdown,
    WeightBreakdown, AccountState, RiskDecision,
)
from services.config import settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_signal(
    signal="BUY",
    confidence=0.6,
    price=50_000.0,
    atr=200.0,
    rsi=35.0,
    ma=49_000.0,
    ma200=48_000.0,
    regime="TRENDING",
) -> SignalResponse:
    return SignalResponse(
        symbol="BTCUSDT",
        interval="5m",
        signal=signal,
        score=0.55,
        confidence=confidence,
        regime=regime,
        threshold=0.5,
        indicators=IndicatorValues(
            rsi=rsi, ma=ma, ma200=ma200, atr=atr, price=price,
        ),
        factors=FactorBreakdown(
            momentum=0.3, trend=0.2, trend_strength=1.0, volatility=0.8,
        ),
        weights=WeightBreakdown(
            momentum=0.2, trend=0.4, trend_strength=0.3, volatility=0.1,
        ),
        reason=["Test signal"],
    )


def make_account(
    balance=10_000.0, peak=10_000.0, active=0,
    exposure=0.0, open_symbols=None,
) -> AccountState:
    return AccountState(
        balance=balance,
        peak_balance=peak,
        active_trades=active,
        current_exposure=exposure,
        open_symbols=open_symbols or [],
    )


# ── 1. Filter Tests ──────────────────────────────────────────────────────────

class TestSignalFilter:
    def test_buy_actionable(self):
        assert check_signal_actionable("BUY")[0] is True

    def test_sell_actionable(self):
        assert check_signal_actionable("SELL")[0] is True

    def test_hold_blocked(self):
        ok, reason = check_signal_actionable("HOLD")
        assert ok is False
        assert "HOLD" in reason


class TestConfidenceFilter:
    def test_high_passes(self):
        assert check_confidence(0.6)[0] is True

    def test_low_blocked(self):
        ok, reason = check_confidence(0.1)
        assert ok is False
        assert "Confidence" in reason

    def test_exact_threshold_passes(self):
        assert check_confidence(0.3)[0] is True

    def test_just_below_blocked(self):
        assert check_confidence(0.299)[0] is False


class TestVolatilityFilter:
    def test_normal_passes(self):
        assert check_volatility(200.0, 50_000.0)[0] is True

    def test_extreme_blocked(self):
        ok, reason = check_volatility(3000.0, 50_000.0)
        assert ok is False
        assert "Volatility" in reason

    def test_zero_price_blocked(self):
        assert check_volatility(100.0, 0.0)[0] is False


class TestActiveTradesFilter:
    def test_zero_passes(self):
        assert check_active_trades(0)[0] is True

    def test_below_max_passes(self):
        assert check_active_trades(2)[0] is True

    def test_at_max_blocked(self):
        ok, reason = check_active_trades(3)
        assert ok is False
        assert "Max active trades" in reason


class TestDrawdownFilter:
    def test_no_drawdown_passes(self):
        assert check_drawdown(10_000.0, 10_000.0)[0] is True

    def test_small_drawdown_passes(self):
        assert check_drawdown(9_500.0, 10_000.0)[0] is True

    def test_at_limit_blocked(self):
        ok, reason = check_drawdown(9_000.0, 10_000.0)
        assert ok is False
        assert "Circuit breaker" in reason

    def test_zero_peak_blocked(self):
        assert check_drawdown(10_000.0, 0.0)[0] is False


class TestPortfolioExposure:
    def test_within_limit_passes(self):
        ok, _ = check_portfolio_exposure(1000.0, 500.0, 10_000.0)
        assert ok is True

    def test_exceeds_limit_blocked(self):
        ok, reason = check_portfolio_exposure(2500.0, 1000.0, 10_000.0)
        assert ok is False
        assert "exposure" in reason.lower()

    def test_at_limit_blocked(self):
        # 3000 + 1 > 3000 (30% of 10000)
        ok, _ = check_portfolio_exposure(3000.0, 1.0, 10_000.0)
        assert ok is False

    def test_zero_exposure_passes(self):
        ok, _ = check_portfolio_exposure(0.0, 2000.0, 10_000.0)
        assert ok is True


class TestCorrelation:
    def test_new_symbol_passes(self):
        ok, _ = check_correlation("BTCUSDT", ["ETHUSDT", "SOLUSDT"])
        assert ok is True

    def test_duplicate_blocked(self):
        ok, reason = check_correlation("BTCUSDT", ["BTCUSDT", "ETHUSDT"])
        assert ok is False
        assert "Duplicate" in reason

    def test_empty_list_passes(self):
        ok, _ = check_correlation("BTCUSDT", [])
        assert ok is True


# ── 2. Position Sizing (Risk-Based) ──────────────────────────────────────────

class TestPositionSizing:
    def test_large_stop_small_position(self):
        """Wide stop loss → smaller position size."""
        size_wide = compute_position_size(10_000.0, 1000.0, 1.0)
        size_narrow = compute_position_size(10_000.0, 100.0, 1.0)
        assert size_wide < size_narrow

    def test_small_stop_large_position(self):
        """Narrow stop loss → larger position size."""
        size = compute_position_size(10_000.0, 50.0, 1.0)
        # 10000 * 0.01 / 50 = 2.0
        assert size == 2.0

    def test_basic_calculation(self):
        """10K * 1% / 400 * 0.6 confidence = 0.15"""
        size = compute_position_size(10_000.0, 400.0, 0.6)
        # risk=100, 100/400=0.25, *0.6=0.15
        assert size == pytest.approx(0.15)

    def test_confidence_modifier(self):
        """Higher confidence → larger position."""
        size_high = compute_position_size(10_000.0, 400.0, 1.0)
        size_low = compute_position_size(10_000.0, 400.0, 0.3)
        assert size_high > size_low

    def test_never_exceeds_cap(self):
        """Position capped at 10% of balance."""
        size = compute_position_size(10_000.0, 0.01, 1.0)
        assert size <= 1_000.0

    def test_zero_stop_returns_zero(self):
        assert compute_position_size(10_000.0, 0.0, 1.0) == 0.0

    def test_zero_confidence_returns_zero(self):
        assert compute_position_size(10_000.0, 400.0, 0.0) == 0.0


class TestPositionUnits:
    def test_basic_units(self):
        """$500 at $50000/unit = 0.01 units."""
        units = compute_position_units(500.0, 50_000.0)
        assert units == pytest.approx(0.01)

    def test_zero_price_returns_zero(self):
        assert compute_position_units(500.0, 0.0) == 0.0


# ── 3. Risk Consistency ─────────────────────────────────────────────────────

class TestRiskConsistency:
    def test_actual_risk_within_limit(self):
        """actual_risk = position_size * sl_distance ≤ risk_amount."""
        balance = 10_000.0
        sl_distance = 400.0
        position = compute_position_size(balance, sl_distance, 0.8)
        actual_risk = position * sl_distance
        max_risk = balance * settings.max_risk_per_trade
        assert actual_risk <= max_risk * 1.001

    def test_risk_same_across_different_stops(self):
        """Different stop distances → same risk amount."""
        balance = 10_000.0
        confidence = 1.0
        risk_amount = balance * settings.max_risk_per_trade

        pos1 = compute_position_size(balance, 100.0, confidence)
        pos2 = compute_position_size(balance, 500.0, confidence)

        risk1 = pos1 * 100.0
        risk2 = pos2 * 500.0

        # Both should risk the same amount (or be capped)
        assert risk1 == pytest.approx(risk_amount, rel=0.01) or pos1 == balance * settings.max_position_pct
        assert risk2 == pytest.approx(risk_amount, rel=0.01) or pos2 == balance * settings.max_position_pct

    def test_validate_risk_returns_actual(self):
        actual = validate_risk_consistency(0.25, 400.0, 10_000.0)
        assert actual == 100.0  # 0.25 * 400 = 100


# ── 4. Stop Loss / Take Profit ──────────────────────────────────────────────

class TestStopLoss:
    def test_buy_stop_below(self):
        assert compute_stop_loss(50_000.0, 200.0, "BUY") == 49_600.0

    def test_sell_stop_above(self):
        assert compute_stop_loss(50_000.0, 200.0, "SELL") == 50_400.0

    def test_buy_stop_never_negative(self):
        assert compute_stop_loss(100.0, 200.0, "BUY") >= 0.0

    def test_hold_returns_zero(self):
        assert compute_stop_loss(50_000.0, 200.0, "HOLD") == 0.0

    def test_stop_loss_distance(self):
        sl = compute_stop_loss(50_000.0, 200.0, "BUY")
        dist = compute_stop_loss_distance(50_000.0, sl)
        assert dist == 400.0  # ATR=200 * multiplier=2


class TestTakeProfit:
    def test_buy_tp_above(self):
        assert compute_take_profit(50_000.0, 200.0, "BUY") == 50_800.0

    def test_sell_tp_below(self):
        assert compute_take_profit(50_000.0, 200.0, "SELL") == 49_200.0

    def test_risk_reward_is_2x(self):
        sl = compute_stop_loss(50_000.0, 200.0, "BUY")
        tp = compute_take_profit(50_000.0, 200.0, "BUY")
        sl_dist = 50_000.0 - sl
        tp_dist = tp - 50_000.0
        assert tp_dist / sl_dist == pytest.approx(2.0)


# ── 5. Trailing Stops ────────────────────────────────────────────────────────

class TestTrailingStops:
    def test_buy_breakeven_trigger(self):
        """BUY: breakeven trigger = entry + 1R."""
        ts = compute_trailing_stops(50_000.0, 200.0, "BUY")
        # 1R = 200 * 2 = 400
        assert ts.breakeven_trigger == 50_400.0

    def test_buy_trail_trigger(self):
        """BUY: trail trigger = entry + 2R."""
        ts = compute_trailing_stops(50_000.0, 200.0, "BUY")
        assert ts.trail_trigger == 50_800.0

    def test_buy_breakeven_stop_at_entry(self):
        """At breakeven, stop moves to entry price."""
        ts = compute_trailing_stops(50_000.0, 200.0, "BUY")
        assert ts.breakeven_stop == 50_000.0

    def test_buy_trail_stop_locks_1r(self):
        """At 2R, trailing stop locks 1R profit."""
        ts = compute_trailing_stops(50_000.0, 200.0, "BUY")
        assert ts.trail_stop == 50_400.0

    def test_sell_breakeven_trigger(self):
        """SELL: breakeven trigger = entry - 1R."""
        ts = compute_trailing_stops(50_000.0, 200.0, "SELL")
        assert ts.breakeven_trigger == 49_600.0

    def test_sell_trail_trigger(self):
        """SELL: trail trigger = entry - 2R."""
        ts = compute_trailing_stops(50_000.0, 200.0, "SELL")
        assert ts.trail_trigger == 49_200.0

    def test_sell_trail_stop_locks_1r(self):
        """SELL trailing stop at entry - 1R (higher price = tighter stop)."""
        ts = compute_trailing_stops(50_000.0, 200.0, "SELL")
        assert ts.trail_stop == 49_600.0

    def test_hold_returns_zeros(self):
        ts = compute_trailing_stops(50_000.0, 200.0, "HOLD")
        assert ts.breakeven_trigger == 0.0


# ── 6. Full Pipeline Integration ─────────────────────────────────────────────

class TestEvaluateRisk:
    def test_buy_executes(self):
        sig = make_signal(signal="BUY", confidence=0.6, atr=200.0, price=50_000.0)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.execute is True
        assert result.signal == "BUY"
        assert result.position_size > 0
        assert result.stop_loss > 0
        assert result.take_profit > 0
        assert result.risk_amount > 0
        assert result.stop_loss_distance > 0
        assert result.position_units > 0

    def test_sell_executes(self):
        sig = make_signal(signal="SELL", confidence=0.5)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.execute is True

    def test_hold_skipped(self):
        sig = make_signal(signal="HOLD")
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.execute is False

    def test_low_confidence_skipped(self):
        sig = make_signal(signal="BUY", confidence=0.1)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.execute is False
        assert "Confidence" in result.reason

    def test_high_volatility_skipped(self):
        sig = make_signal(signal="BUY", confidence=0.8, atr=3000.0)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.execute is False

    def test_max_trades_skipped(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account(active=3)
        result = evaluate_risk(sig, acc)
        assert result.execute is False

    def test_drawdown_circuit_breaker(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account(balance=8_000.0, peak=10_000.0)
        result = evaluate_risk(sig, acc)
        assert result.execute is False
        assert "Circuit breaker" in result.reason

    def test_duplicate_symbol_blocked(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account(open_symbols=["BTCUSDT"])
        result = evaluate_risk(sig, acc)
        assert result.execute is False
        assert "Duplicate" in result.reason

    def test_exposure_limit_blocked(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account(exposure=2999.0)  # near 30% limit
        result = evaluate_risk(sig, acc)
        # Should block since adding position would exceed 30%
        assert result.execute is False or result.exposure_after_trade <= 3000.0

    def test_stop_loss_distance_in_output(self):
        sig = make_signal(signal="BUY", price=50_000.0, atr=200.0)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.stop_loss_distance == 400.0  # ATR*2

    def test_trailing_stops_present(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.trailing_stops is not None
        assert result.trailing_stops.breakeven_trigger > 0

    def test_risk_reward_ratio_returned(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.risk_reward_ratio == 2.0

    def test_exposure_after_trade_calculated(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account(exposure=500.0)
        result = evaluate_risk(sig, acc)
        if result.execute:
            assert result.exposure_after_trade == pytest.approx(
                500.0 + result.position_size
            )

    def test_determinism(self):
        sig = make_signal(signal="BUY", confidence=0.7)
        acc = make_account()
        r1 = evaluate_risk(sig, acc)
        r2 = evaluate_risk(sig, acc)
        assert r1.execute == r2.execute
        assert r1.position_size == r2.position_size
        assert r1.stop_loss == r2.stop_loss
        assert r1.take_profit == r2.take_profit
        assert r1.risk_amount == r2.risk_amount

    def test_skipped_trade_zero_position(self):
        sig = make_signal(signal="HOLD")
        acc = make_account()
        result = evaluate_risk(sig, acc)
        assert result.position_size == 0.0

    def test_symbol_propagated(self):
        sig = make_signal(signal="BUY", confidence=0.6)
        acc = make_account()
        assert evaluate_risk(sig, acc).symbol == "BTCUSDT"

    def test_regime_propagated(self):
        sig = make_signal(signal="BUY", confidence=0.6, regime="SIDEWAYS")
        acc = make_account()
        assert evaluate_risk(sig, acc).regime == "SIDEWAYS"

    def test_actual_risk_never_exceeds_limit(self):
        """Core invariant: actual dollar risk ≤ 1% of balance."""
        for atr in [50.0, 200.0, 500.0, 1000.0]:
            sig = make_signal(signal="BUY", confidence=0.8, atr=atr, price=50_000.0)
            acc = make_account(balance=10_000.0)
            result = evaluate_risk(sig, acc)
            if result.execute:
                actual_risk = result.position_size * result.stop_loss_distance
                max_risk = 10_000.0 * settings.max_risk_per_trade
                assert actual_risk <= max_risk * 1.001
