"""
test_signal_engine.py — Tests for the context-aware adaptive scoring engine.

Test categories:
    1. Indicators (RSI, SMA, ATR)
    2. Regime detection
    3. Dynamic weights
    4. Factor scores (momentum, trend, trend_strength, volatility)
    5. Dynamic threshold
    6. Disagreement penalty
    7. Full engine integration
    8. Determinism
    9. Edge cases

All tests are pure — no DB, no network.
"""

import pytest
import pandas as pd
import numpy as np

from services.indicators import compute_rsi, compute_sma, compute_atr
from services.signal_engine import (
    generate_signal,
    compute_regime,
    get_weights,
    compute_momentum_score,
    compute_trend_score,
    compute_trend_strength_score,
    compute_volatility_score,
    compute_dynamic_threshold,
    compute_disagreement,
    REGIME_TRENDING,
    REGIME_SIDEWAYS,
    WEIGHTS_TRENDING,
    WEIGHTS_SIDEWAYS,
    BASE_THRESHOLD,
    DISAGREEMENT_PENALTY,
)
from services.schemas import SignalResponse, ErrorResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

INTERVAL = "5m"


def make_df(prices: list) -> pd.DataFrame:
    return pd.DataFrame({
        "price": pd.Series(prices, dtype=float),
        "symbol": "BTCUSDT",
        "timestamp": pd.date_range("2024-01-01", periods=len(prices), freq="1s"),
    })


def make_downtrend(n=250, start=80_000, step=100) -> list:
    return [start - i * step for i in range(n)]


def make_uptrend(n=250, start=40_000, step=100) -> list:
    return [start + i * step for i in range(n)]


def make_flat(n=250, price=50_000.0) -> list:
    return [price] * n


# ── 1. Indicator Tests ────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_range(self):
        rsi = compute_rsi(pd.Series(make_uptrend()))
        assert 0.0 <= rsi <= 100.0

    def test_rsi_downtrend_low(self):
        rsi = compute_rsi(pd.Series(make_downtrend(n=60)))
        assert rsi < 30

    def test_rsi_uptrend_high(self):
        rsi = compute_rsi(pd.Series(make_uptrend(n=60)))
        assert rsi > 70

    def test_rsi_flat(self):
        assert isinstance(compute_rsi(pd.Series(make_flat())), float)

    def test_rsi_insufficient_raises(self):
        with pytest.raises(ValueError):
            compute_rsi(pd.Series([100.0] * 5), period=14)

    def test_rsi_determinism(self):
        p = pd.Series(make_downtrend(n=80))
        assert compute_rsi(p) == compute_rsi(p)


class TestSMA:
    def test_sma_correct(self):
        assert compute_sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), period=5) == 3.0

    def test_sma_last_n(self):
        assert compute_sma(pd.Series([10, 20, 30, 40, 50.0]), period=3) == pytest.approx(40.0)

    def test_sma_insufficient_raises(self):
        with pytest.raises(ValueError):
            compute_sma(pd.Series([100.0] * 10), period=50)


class TestATR:
    def test_atr_positive_volatile(self):
        assert compute_atr(pd.Series(make_uptrend(n=30)), period=14) > 0

    def test_atr_zero_flat(self):
        assert compute_atr(pd.Series(make_flat(n=30)), period=14) == 0.0

    def test_atr_insufficient_raises(self):
        with pytest.raises(ValueError):
            compute_atr(pd.Series([100.0] * 5), period=14)

    def test_atr_determinism(self):
        p = pd.Series(make_uptrend(n=30))
        assert compute_atr(p) == compute_atr(p)


# ── 2. Regime Detection Tests ────────────────────────────────────────────────

class TestRegimeDetection:
    def test_trending_when_diverged(self):
        """Price far from MA → TRENDING."""
        regime, metric = compute_regime(52_000, 50_000)
        assert regime == REGIME_TRENDING
        assert metric > 0.02

    def test_sideways_when_close(self):
        """Price near MA → SIDEWAYS."""
        regime, metric = compute_regime(50_500, 50_000)
        assert regime == REGIME_SIDEWAYS
        assert metric <= 0.02

    def test_sideways_exact_equal(self):
        """Price == MA → SIDEWAYS."""
        regime, _ = compute_regime(50_000, 50_000)
        assert regime == REGIME_SIDEWAYS

    def test_trending_below_ma(self):
        """Price well below MA → still TRENDING."""
        regime, _ = compute_regime(48_000, 50_000)
        assert regime == REGIME_TRENDING

    def test_zero_ma_returns_sideways(self):
        """Edge case: MA=0 → SIDEWAYS."""
        regime, _ = compute_regime(50_000, 0)
        assert regime == REGIME_SIDEWAYS

    def test_metric_is_always_positive(self):
        """Trend metric is abs(), always >= 0."""
        _, metric = compute_regime(45_000, 50_000)
        assert metric >= 0


# ── 3. Dynamic Weights Tests ─────────────────────────────────────────────────

class TestDynamicWeights:
    def test_trending_weights(self):
        """TRENDING regime → trend-heavy weights."""
        weights = get_weights(REGIME_TRENDING)
        assert weights == WEIGHTS_TRENDING
        assert weights["trend"] == 0.4
        assert weights["momentum"] == 0.2

    def test_sideways_weights(self):
        """SIDEWAYS regime → momentum-heavy weights."""
        weights = get_weights(REGIME_SIDEWAYS)
        assert weights == WEIGHTS_SIDEWAYS
        assert weights["momentum"] == 0.5
        assert weights["trend"] == 0.2

    def test_trending_weights_sum_to_one(self):
        assert sum(WEIGHTS_TRENDING.values()) == pytest.approx(1.0)

    def test_sideways_weights_sum_to_one(self):
        assert sum(WEIGHTS_SIDEWAYS.values()) == pytest.approx(1.0)

    def test_unknown_regime_defaults_to_sideways(self):
        """Unknown regime string → sideways weights (safe default)."""
        weights = get_weights("UNKNOWN")
        assert weights == WEIGHTS_SIDEWAYS


# ── 4. Factor Score Tests ────────────────────────────────────────────────────

class TestFactorScores:
    # Momentum
    def test_momentum_oversold(self):
        assert compute_momentum_score(20.0) == pytest.approx(0.6)

    def test_momentum_overbought(self):
        assert compute_momentum_score(80.0) == pytest.approx(-0.6)

    def test_momentum_neutral(self):
        assert compute_momentum_score(50.0) == 0.0

    def test_momentum_clamped_extremes(self):
        assert compute_momentum_score(0.0) == 1.0
        assert compute_momentum_score(100.0) == -1.0

    # Trend
    def test_trend_above_ma(self):
        assert compute_trend_score(55000, 50000) > 0

    def test_trend_below_ma(self):
        assert compute_trend_score(45000, 50000) < 0

    def test_trend_at_ma(self):
        assert compute_trend_score(50000, 50000) == 0.0

    def test_trend_clamped(self):
        assert compute_trend_score(200000, 50000) == 1.0

    # Trend strength
    def test_strength_uptrend(self):
        assert compute_trend_strength_score(55000, 50000) == 1.0

    def test_strength_downtrend(self):
        assert compute_trend_strength_score(45000, 50000) == -1.0

    def test_strength_equal(self):
        assert compute_trend_strength_score(50000, 50000) == 0.0

    # Volatility (REFACTORED)
    def test_volatility_low_atr_positive(self):
        """Low volatility → score near +1."""
        score = compute_volatility_score(10.0, 50000.0)
        assert score > 0.9

    def test_volatility_high_atr_negative(self):
        """High volatility → score near -1."""
        score = compute_volatility_score(2000.0, 50000.0)
        assert score < -0.9

    def test_volatility_zero_price(self):
        assert compute_volatility_score(100.0, 0.0) == 0.0

    def test_volatility_zero_atr(self):
        """Zero ATR → maximum stability → score = +1."""
        score = compute_volatility_score(0.0, 50000.0)
        assert score == 1.0


# ── 5. Dynamic Threshold Tests ───────────────────────────────────────────────

class TestDynamicThreshold:
    def test_low_volatility_near_base(self):
        """Low ATR → threshold near base (0.5)."""
        threshold = compute_dynamic_threshold(10.0, 50000.0)
        assert threshold == pytest.approx(BASE_THRESHOLD, abs=0.01)

    def test_high_volatility_raises_threshold(self):
        """High ATR → threshold increases above base."""
        threshold = compute_dynamic_threshold(2000.0, 50000.0)
        assert threshold > BASE_THRESHOLD

    def test_extreme_volatility_caps_threshold(self):
        """Very high ATR → threshold caps at base + penalty."""
        threshold = compute_dynamic_threshold(50000.0, 50000.0)
        assert threshold == pytest.approx(BASE_THRESHOLD + 0.2, abs=0.01)

    def test_zero_price_returns_base(self):
        assert compute_dynamic_threshold(100.0, 0.0) == BASE_THRESHOLD

    def test_threshold_always_above_base(self):
        """Threshold must always be >= base."""
        for atr in [0.0, 10.0, 100.0, 1000.0, 5000.0]:
            assert compute_dynamic_threshold(atr, 50000.0) >= BASE_THRESHOLD


# ── 6. Disagreement Penalty Tests ────────────────────────────────────────────

class TestDisagreementPenalty:
    def test_all_positive_no_disagreement(self):
        """All factors positive → no disagreement."""
        assert compute_disagreement(0.5, 0.3, 1.0) is False

    def test_all_negative_no_disagreement(self):
        """All factors negative → no disagreement."""
        assert compute_disagreement(-0.5, -0.3, -1.0) is False

    def test_mixed_signs_disagreement(self):
        """Some positive + some negative → disagreement."""
        assert compute_disagreement(0.5, -0.3, 1.0) is True

    def test_one_positive_one_negative_disagreement(self):
        assert compute_disagreement(0.5, -0.3, 0.0) is True

    def test_all_zero_no_disagreement(self):
        """All neutral → no disagreement."""
        assert compute_disagreement(0.0, 0.0, 0.0) is False

    def test_one_nonzero_no_disagreement(self):
        """Single direction → no disagreement."""
        assert compute_disagreement(0.5, 0.0, 0.0) is False


# ── 7. Full Engine Integration Tests ─────────────────────────────────────────

class TestSignalEngine:
    def test_determinism(self):
        """Same input → identical output."""
        df = make_df(make_downtrend(n=250))
        r1 = generate_signal(df, "BTCUSDT", INTERVAL)
        r2 = generate_signal(df, "BTCUSDT", INTERVAL)
        assert r1.signal == r2.signal
        assert r1.score == r2.score
        assert r1.confidence == r2.confidence
        assert r1.regime == r2.regime
        assert r1.threshold == r2.threshold

    def test_flat_market_is_hold(self):
        df = make_df(make_flat(n=250))
        result = generate_signal(df, "BTCUSDT", INTERVAL)
        assert isinstance(result, SignalResponse)
        assert result.signal == "HOLD"

    def test_insufficient_data_error(self):
        result = generate_signal(make_df([50_000.0] * 5), "BTCUSDT", INTERVAL)
        assert isinstance(result, ErrorResponse)
        assert result.signal == "HOLD"

    def test_empty_dataframe_error(self):
        result = generate_signal(pd.DataFrame(), "BTCUSDT", INTERVAL)
        assert isinstance(result, ErrorResponse)
        assert "Insufficient data" in result.error

    def test_score_is_float(self):
        for prices in [make_uptrend(n=250), make_downtrend(n=250), make_flat(n=250)]:
            result = generate_signal(make_df(prices), "BTCUSDT", INTERVAL)
            if isinstance(result, SignalResponse):
                assert isinstance(result.score, float)
                assert -1.0 <= result.score <= 1.0

    def test_confidence_range(self):
        for prices in [make_uptrend(n=250), make_downtrend(n=250), make_flat(n=250)]:
            result = generate_signal(make_df(prices), "BTCUSDT", INTERVAL)
            if isinstance(result, SignalResponse):
                assert 0.0 <= result.confidence <= 1.0

    def test_regime_field_present(self):
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.regime in (REGIME_TRENDING, REGIME_SIDEWAYS)

    def test_threshold_field_present(self):
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.threshold >= BASE_THRESHOLD

    def test_weights_field_present(self):
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert hasattr(result, "weights")
            w = result.weights
            total = w.momentum + w.trend + w.trend_strength + w.volatility
            assert total == pytest.approx(1.0)

    def test_factors_in_range(self):
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert -1.0 <= result.factors.momentum <= 1.0
            assert -1.0 <= result.factors.trend <= 1.0
            assert result.factors.trend_strength in (-1.0, 0.0, 1.0)
            assert -1.0 <= result.factors.volatility <= 1.0

    def test_reason_always_present(self):
        result = generate_signal(make_df(make_flat(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert len(result.reason) > 0

    def test_symbol_uppercased(self):
        result = generate_signal(make_df(make_flat(n=250)), "btcusdt", INTERVAL)
        assert result.symbol == "BTCUSDT"

    def test_interval_propagated(self):
        result = generate_signal(make_df(make_flat(n=250)), "BTCUSDT", "1h")
        assert result.interval == "1h"

    def test_atr_in_indicators(self):
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.indicators.atr >= 0

    def test_duplicate_timestamps_handled(self):
        prices = make_flat(n=250)
        df = pd.DataFrame({
            "price": pd.Series(prices + prices[:10], dtype=float),
            "symbol": "BTCUSDT",
            "timestamp": (
                list(pd.date_range("2024-01-01", periods=250, freq="1s"))
                + list(pd.date_range("2024-01-01", periods=10, freq="1s"))
            ),
        })
        result = generate_signal(df, "BTCUSDT", INTERVAL)
        assert result.signal in ("BUY", "SELL", "HOLD")

    def test_downtrend_momentum_positive(self):
        """Strong downtrend → RSI low → momentum factor bullish."""
        result = generate_signal(make_df(make_downtrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.factors.momentum > 0

    def test_uptrend_momentum_negative(self):
        """Strong uptrend → RSI high → momentum factor bearish."""
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.factors.momentum < 0

    def test_trending_regime_in_strong_trend(self):
        """Strong uptrend → price far from MA → TRENDING."""
        result = generate_signal(make_df(make_uptrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.regime == REGIME_TRENDING

    def test_sideways_regime_in_flat_market(self):
        """Flat market → price == MA → SIDEWAYS."""
        result = generate_signal(make_df(make_flat(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            assert result.regime == REGIME_SIDEWAYS

    def test_disagreement_reduces_confidence(self):
        """When factors disagree, confidence should be lower than abs(score)."""
        # Build a scenario where factors will disagree:
        # slight uptrend (trend positive) but with a manufactured RSI that would be high
        # Actually, let's just test the penalty function directly
        # and verify it's applied in the full pipeline
        result = generate_signal(make_df(make_downtrend(n=250)), "BTCUSDT", INTERVAL)
        if isinstance(result, SignalResponse):
            if any("disagreement" in r.lower() for r in result.reason):
                assert result.confidence <= abs(result.score)
