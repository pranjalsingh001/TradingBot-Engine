"""
test_portfolio_engine.py — Tests for the coordinated portfolio allocation engine.

Test categories:
    1. Filtering (invalid trades removed)
    2. Ranking (confidence-based ordering)
    3. Correlation control (1 per category)
    4. Max positions enforced
    5. Risk scaling (proportional reduction)
    6. Allocation weights (score-weighted)
    7. Full pipeline integration
    8. Determinism
    9. Edge cases

All tests are pure — no DB, no network.
"""

import pytest

from services.portfolio_engine import (
    filter_candidates,
    rank_trades,
    apply_correlation_filter,
    select_top,
    compute_risk_scaling,
    compute_allocation_weights,
    allocate_portfolio,
    get_asset_category,
)
from services.schemas import RiskDecision, TrailingStopLevels


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trade(
    symbol="BTCUSDT",
    signal="BUY",
    execute=True,
    confidence=0.6,
    position_size=100.0,
    risk_amount=100.0,
    stop_loss_distance=400.0,
    regime="TRENDING",
) -> RiskDecision:
    return RiskDecision(
        execute=execute,
        reason="test",
        signal=signal,
        symbol=symbol,
        interval="5m",
        position_size=position_size,
        position_units=0.002,
        entry_price=50_000.0,
        stop_loss=49_600.0,
        take_profit=50_800.0,
        risk_reward_ratio=2.0,
        risk_amount=risk_amount,
        stop_loss_distance=stop_loss_distance,
        exposure_after_trade=0.0,
        confidence=confidence,
        regime=regime,
    )


# ── 1. Filter Tests ──────────────────────────────────────────────────────────

class TestFilter:
    def test_removes_hold(self):
        trades = [make_trade(signal="HOLD"), make_trade(signal="BUY")]
        result = filter_candidates(trades)
        assert len(result) == 1
        assert result[0].signal == "BUY"

    def test_removes_non_execute(self):
        trades = [make_trade(execute=False), make_trade(execute=True)]
        result = filter_candidates(trades)
        assert len(result) == 1

    def test_removes_low_confidence(self):
        trades = [make_trade(confidence=0.1), make_trade(confidence=0.5)]
        result = filter_candidates(trades)
        assert len(result) == 1
        assert result[0].confidence == 0.5

    def test_keeps_valid_trades(self):
        trades = [make_trade(), make_trade(symbol="ETHUSDT")]
        result = filter_candidates(trades)
        assert len(result) == 2

    def test_empty_input(self):
        assert filter_candidates([]) == []


# ── 2. Ranking Tests ─────────────────────────────────────────────────────────

class TestRanking:
    def test_highest_confidence_first(self):
        trades = [
            make_trade(symbol="SOLUSDT", confidence=0.4),
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="ETHUSDT", confidence=0.6),
        ]
        ranked = rank_trades(trades)
        assert ranked[0].symbol == "BTCUSDT"
        assert ranked[1].symbol == "ETHUSDT"
        assert ranked[2].symbol == "SOLUSDT"

    def test_single_trade(self):
        trades = [make_trade()]
        assert len(rank_trades(trades)) == 1

    def test_empty_input(self):
        assert rank_trades([]) == []


# ── 3. Correlation Control Tests ─────────────────────────────────────────────

class TestCorrelation:
    def test_duplicate_symbol_removed(self):
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="BTCUSDT", confidence=0.5),
        ]
        result = apply_correlation_filter(trades)
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_same_category_removed(self):
        """BTC and ETH are both crypto_major — only first kept."""
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="ETHUSDT", confidence=0.8),
        ]
        result = apply_correlation_filter(trades)
        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    def test_different_categories_kept(self):
        """BTC (major) and SOL (alt) → both kept."""
        trades = [
            make_trade(symbol="BTCUSDT"),
            make_trade(symbol="SOLUSDT"),
        ]
        result = apply_correlation_filter(trades)
        assert len(result) == 2

    def test_unknown_symbol_gets_other_category(self):
        assert get_asset_category("UNKNOWNUSDT") == "other"

    def test_known_categories(self):
        assert get_asset_category("BTCUSDT") == "crypto_major"
        assert get_asset_category("ETHUSDT") == "crypto_major"
        assert get_asset_category("SOLUSDT") == "crypto_alt"
        assert get_asset_category("ADAUSDT") == "crypto_alt"

    def test_multiple_alts_only_one_kept(self):
        """SOL, ADA, AVAX are all crypto_alt — only first kept."""
        trades = [
            make_trade(symbol="SOLUSDT", confidence=0.8),
            make_trade(symbol="ADAUSDT", confidence=0.7),
            make_trade(symbol="AVAXUSDT", confidence=0.6),
        ]
        result = apply_correlation_filter(trades)
        assert len(result) == 1
        assert result[0].symbol == "SOLUSDT"


# ── 4. Max Positions Tests ───────────────────────────────────────────────────

class TestSelectTop:
    def test_selects_top_n(self):
        trades = [make_trade(symbol=f"SYM{i}") for i in range(5)]
        result = select_top(trades, 3)
        assert len(result) == 3

    def test_fewer_than_max(self):
        trades = [make_trade()]
        result = select_top(trades, 3)
        assert len(result) == 1

    def test_empty_input(self):
        assert select_top([], 3) == []


# ── 5. Risk Scaling Tests ────────────────────────────────────────────────────

class TestRiskScaling:
    def test_within_limit_no_scaling(self):
        trades = [make_trade(risk_amount=50.0)]
        factor, _ = compute_risk_scaling(trades, 10_000.0, 0.03)
        assert factor == 1.0

    def test_exceeds_limit_scales_down(self):
        """3 trades × $150 = $450 > $300 (3% of 10K)."""
        trades = [make_trade(risk_amount=150.0) for _ in range(3)]
        factor, raw = compute_risk_scaling(trades, 10_000.0, 0.03)
        assert factor < 1.0
        assert factor == pytest.approx(300.0 / 450.0, rel=0.001)

    def test_exact_limit_no_scaling(self):
        trades = [make_trade(risk_amount=100.0) for _ in range(3)]
        factor, _ = compute_risk_scaling(trades, 10_000.0, 0.03)
        assert factor == 1.0

    def test_zero_risk(self):
        trades = [make_trade(risk_amount=0.0)]
        factor, _ = compute_risk_scaling(trades, 10_000.0, 0.03)
        assert factor == 1.0

    def test_scaled_risk_within_limit(self):
        """After scaling, total risk must be ≤ limit."""
        trades = [make_trade(risk_amount=200.0) for _ in range(3)]
        factor, _ = compute_risk_scaling(trades, 10_000.0, 0.03)
        scaled_total = sum(200.0 * factor for _ in range(3))
        assert scaled_total <= 300.0 * 1.001


# ── 6. Allocation Weight Tests ──────────────────────────────────────────────

class TestAllocationWeights:
    def test_weights_sum_to_one(self):
        trades = [
            make_trade(confidence=0.8),
            make_trade(confidence=0.4),
        ]
        weights = compute_allocation_weights(trades)
        assert sum(weights) == pytest.approx(1.0, abs=0.001)

    def test_higher_confidence_gets_more_weight(self):
        trades = [
            make_trade(confidence=0.9),
            make_trade(confidence=0.3),
        ]
        weights = compute_allocation_weights(trades)
        assert weights[0] > weights[1]

    def test_single_trade_gets_full_weight(self):
        trades = [make_trade(confidence=0.5)]
        weights = compute_allocation_weights(trades)
        assert weights[0] == pytest.approx(1.0)

    def test_equal_confidence_equal_weights(self):
        trades = [make_trade(confidence=0.5), make_trade(confidence=0.5)]
        weights = compute_allocation_weights(trades)
        assert weights[0] == pytest.approx(weights[1])


# ── 7. Full Pipeline Integration ─────────────────────────────────────────────

class TestAllocatePortfolio:
    def test_basic_allocation(self):
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.8, risk_amount=80),
            make_trade(symbol="SOLUSDT", confidence=0.6, risk_amount=60),
        ]
        result = allocate_portfolio(trades, 10_000.0)
        assert result.portfolio.total_positions == 2
        assert result.portfolio.total_risk > 0
        assert result.portfolio.total_risk <= result.portfolio.max_allowed_risk

    def test_empty_candidates(self):
        result = allocate_portfolio([], 10_000.0)
        assert result.portfolio.total_positions == 0
        assert result.selected_trades == []

    def test_all_invalid_candidates(self):
        trades = [make_trade(signal="HOLD"), make_trade(execute=False)]
        result = allocate_portfolio(trades, 10_000.0)
        assert result.portfolio.total_positions == 0

    def test_max_positions_enforced(self):
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="SOLUSDT", confidence=0.8),
            make_trade(symbol="DOGEUSDT", confidence=0.7),
            make_trade(symbol="UNKNOWNA", confidence=0.6),
            make_trade(symbol="UNKNOWNB", confidence=0.5),
        ]
        result = allocate_portfolio(trades, 10_000.0, max_positions=3)
        assert result.portfolio.total_positions <= 3

    def test_correlation_applied(self):
        """BTC and ETH in same category → only 1 selected."""
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="ETHUSDT", confidence=0.8),
            make_trade(symbol="SOLUSDT", confidence=0.7),
        ]
        result = allocate_portfolio(trades, 10_000.0)
        symbols = [t.symbol for t in result.selected_trades]
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" not in symbols
        assert "SOLUSDT" in symbols

    def test_risk_never_exceeds_limit(self):
        """Total risk must never exceed max_portfolio_risk."""
        trades = [
            make_trade(symbol="BTCUSDT", risk_amount=200, confidence=0.9),
            make_trade(symbol="SOLUSDT", risk_amount=200, confidence=0.8),
            make_trade(symbol="DOGEUSDT", risk_amount=200, confidence=0.7),
        ]
        result = allocate_portfolio(trades, 10_000.0, max_risk_pct=0.03)
        assert result.portfolio.total_risk <= 300.0 * 1.001

    def test_risk_scaling_applied(self):
        """When total risk > limit, scale_factor < 1."""
        trades = [
            make_trade(symbol="BTCUSDT", risk_amount=200, confidence=0.9),
            make_trade(symbol="SOLUSDT", risk_amount=200, confidence=0.8),
        ]
        result = allocate_portfolio(trades, 10_000.0, max_risk_pct=0.03)
        if result.portfolio.total_risk > 0:
            # 400 > 300, so scaling should be applied
            assert result.portfolio.scale_factor < 1.0

    def test_allocation_weights_present(self):
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.8),
            make_trade(symbol="SOLUSDT", confidence=0.4),
        ]
        result = allocate_portfolio(trades, 10_000.0)
        total_weight = sum(t.allocation_weight for t in result.selected_trades)
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_higher_confidence_gets_more_weight(self):
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.9),
            make_trade(symbol="SOLUSDT", confidence=0.3),
        ]
        result = allocate_portfolio(trades, 10_000.0)
        btc = next(t for t in result.selected_trades if t.symbol == "BTCUSDT")
        sol = next(t for t in result.selected_trades if t.symbol == "SOLUSDT")
        assert btc.allocation_weight > sol.allocation_weight

    def test_remaining_capacity(self):
        trades = [make_trade(symbol="BTCUSDT", risk_amount=50, confidence=0.6)]
        result = allocate_portfolio(trades, 10_000.0, max_risk_pct=0.03)
        assert result.portfolio.remaining_capacity > 0
        assert result.portfolio.remaining_capacity == pytest.approx(
            300.0 - result.portfolio.total_risk, abs=1.0
        )

    def test_category_in_output(self):
        trades = [make_trade(symbol="BTCUSDT")]
        result = allocate_portfolio(trades, 10_000.0)
        assert result.selected_trades[0].category == "crypto_major"

    def test_determinism(self):
        """Same input → identical output."""
        trades = [
            make_trade(symbol="BTCUSDT", confidence=0.8),
            make_trade(symbol="SOLUSDT", confidence=0.5),
        ]
        r1 = allocate_portfolio(trades, 10_000.0)
        r2 = allocate_portfolio(trades, 10_000.0)
        assert r1.portfolio.total_positions == r2.portfolio.total_positions
        assert r1.portfolio.total_risk == r2.portfolio.total_risk
        assert r1.portfolio.scale_factor == r2.portfolio.scale_factor
        for t1, t2 in zip(r1.selected_trades, r2.selected_trades):
            assert t1.symbol == t2.symbol
            assert t1.position_size == t2.position_size

    def test_custom_max_risk(self):
        trades = [make_trade(symbol="BTCUSDT", risk_amount=100)]
        result = allocate_portfolio(trades, 10_000.0, max_risk_pct=0.01)
        assert result.portfolio.max_allowed_risk == 100.0

    def test_custom_max_positions(self):
        trades = [
            make_trade(symbol="BTCUSDT"),
            make_trade(symbol="SOLUSDT"),
            make_trade(symbol="DOGEUSDT"),
        ]
        result = allocate_portfolio(trades, 10_000.0, max_positions=1)
        assert result.portfolio.total_positions == 1
