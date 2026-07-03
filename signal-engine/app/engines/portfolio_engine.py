"""
portfolio_engine.py — Coordinated portfolio allocation engine.

Takes a list of risk-engine outputs, filters, ranks, applies correlation
control, enforces portfolio-level risk limits, and allocates capital
weighted by signal strength.

Pipeline:
    1. Filter invalid trades
    2. Rank by confidence + score
    3. Apply correlation control (1 trade per asset category)
    4. Select top N
    5. Enforce portfolio risk limit (scale down if needed)
    6. Score-weighted capital allocation

Single responsibility: portfolio allocation only.
No DB calls. No HTTP. No randomness. No order execution.
Does NOT modify signal or risk engine logic.
"""

import logging
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.schemas import (
    RiskDecision, SelectedTrade, PortfolioSummary, PortfolioDecision,
)

logger = logging.getLogger(__name__)

# ── Asset category mapping ───────────────────────────────────────────────────
# Rule-based correlation groups. Only 1 trade per category allowed.

ASSET_CATEGORIES: Dict[str, str] = {
    "BTCUSDT":  "crypto_major",
    "ETHUSDT":  "crypto_major",
    "SOLUSDT":  "crypto_alt",
    "ADAUSDT":  "crypto_alt",
    "AVAXUSDT": "crypto_alt",
    "DOTUSDT":  "crypto_alt",
    "MATICUSDT": "crypto_alt",
    "LINKUSDT": "crypto_alt",
    "XRPUSDT":  "crypto_alt",
    "DOGEUSDT": "crypto_meme",
    "SHIBUSDT": "crypto_meme",
}

DEFAULT_CATEGORY = "other"


def get_asset_category(symbol: str) -> str:
    """Look up asset category for correlation control."""
    return ASSET_CATEGORIES.get(symbol.upper(), DEFAULT_CATEGORY)


# ── Step 1: Filter ───────────────────────────────────────────────────────────

def filter_candidates(trades: List[RiskDecision]) -> List[RiskDecision]:
    """
    Remove non-actionable trades:
        - signal == HOLD
        - execute == False
        - confidence < min_confidence
    """
    valid = []
    for t in trades:
        if t.signal == "HOLD":
            continue
        if not t.execute:
            continue
        if t.confidence < settings.min_confidence:
            continue
        valid.append(t)

    # Removed crashy log line
    return valid


# ── Step 2: Rank ─────────────────────────────────────────────────────────────

def rank_trades(trades: List[RiskDecision]) -> List[RiskDecision]:
    """
    Sort trades by:
        1. confidence (descending)
        2. abs(score) as tiebreaker (descending)

    Deterministic: stable sort, consistent ordering.
    """
    return sorted(
        trades,
        key=lambda t: (t.confidence, abs(getattr(t, "confidence", 0))),
        reverse=True,
    )


# ── Step 3: Correlation control ──────────────────────────────────────────────

def apply_correlation_filter(trades: List[RiskDecision]) -> List[RiskDecision]:
    """
    Enforce:
        - No duplicate symbols
        - Max 1 trade per asset category

    Assumes trades are already ranked (best first).
    """
    seen_symbols: set = set()
    seen_categories: set = set()
    filtered: List[RiskDecision] = []

    for t in trades:
        symbol = t.symbol.upper()
        category = get_asset_category(symbol)

        if symbol in seen_symbols:
            logger.info("[Portfolio] Duplicate symbol skipped: %s", symbol)
            continue

        if category in seen_categories:
            logger.info(
                "[Portfolio] Correlated asset skipped: %s (category=%s)",
                symbol, category,
            )
            continue

        seen_symbols.add(symbol)
        seen_categories.add(category)
        filtered.append(t)

    logger.info(
        "[Portfolio] Correlation filter: %d -> %d",
        len(trades), len(filtered),
    )
    return filtered


# ── Step 4: Select top N ─────────────────────────────────────────────────────

def select_top(
    trades: List[RiskDecision], max_positions: int,
) -> List[RiskDecision]:
    """Take the top N ranked trades."""
    selected = trades[:max_positions]
    logger.info("[Portfolio] Selected top %d of %d", len(selected), len(trades))
    return selected


# ── Step 5: Portfolio risk control ───────────────────────────────────────────

def compute_risk_scaling(
    trades: List[RiskDecision], balance: float, max_risk_pct: float,
) -> Tuple[float, float]:
    """
    Compute scaling factor if total risk exceeds portfolio limit.

    Returns (scale_factor, total_risk_before_scaling)
    """
    total_risk = sum(t.risk_amount for t in trades)
    max_allowed = balance * max_risk_pct

    if total_risk <= 0:
        return 1.0, 0.0

    if total_risk <= max_allowed:
        return 1.0, total_risk

    scale_factor = max_allowed / total_risk
    logger.info(
        "[Portfolio] Risk scaling: total=$%.2f > max=$%.2f → factor=%.4f",
        total_risk, max_allowed, scale_factor,
    )
    return round(scale_factor, 6), total_risk


# ── Step 6: Score-weighted allocation ────────────────────────────────────────

def compute_allocation_weights(
    trades: List[RiskDecision],
) -> List[float]:
    """
    Compute allocation weights proportional to abs(score).

    Stronger signals get proportionally more capital.
    Returns a list of weights that sum to 1.0.
    """
    # Use confidence as the weight basis (more meaningful than raw score)
    total_weight = sum(t.confidence for t in trades)

    if total_weight <= 0:
        n = len(trades)
        return [1.0 / n if n > 0 else 0.0] * n

    return [round(t.confidence / total_weight, 6) for t in trades]


# ── Core engine ──────────────────────────────────────────────────────────────

def allocate_portfolio(
    candidates: List[RiskDecision],
    balance: float,
    max_risk_pct: float = None,
    max_positions: int = None,
) -> PortfolioDecision:
    """
    Core portfolio allocation function.

    Pipeline:
        1. Filter invalid trades
        2. Rank by confidence
        3. Apply correlation control
        4. Select top N
        5. Scale risk if over limit
        6. Score-weighted allocation
        7. Build output

    Parameters
    ----------
    candidates     : list of RiskDecision from risk engine
    balance        : current account balance
    max_risk_pct   : max total portfolio risk (default from config)
    max_positions  : max simultaneous positions (default from config)

    Returns
    -------
    PortfolioDecision with selected trades and portfolio summary
    """
    if max_risk_pct is None:
        max_risk_pct = settings.max_portfolio_risk
    if max_positions is None:
        max_positions = settings.max_positions

    max_allowed_risk = balance * max_risk_pct

    # ── Step 1: Filter ────────────────────────────────────────────────────────
    valid = filter_candidates(candidates)

    if not valid:
        return _empty_portfolio(max_allowed_risk)

    # ── Step 2: Rank ──────────────────────────────────────────────────────────
    ranked = rank_trades(valid)

    # ── Step 3: Correlation control ───────────────────────────────────────────
    uncorrelated = apply_correlation_filter(ranked)

    if not uncorrelated:
        return _empty_portfolio(max_allowed_risk)

    # ── Step 4: Select top N ──────────────────────────────────────────────────
    selected = select_top(uncorrelated, max_positions)

    # ── Step 5: Risk scaling ─────────────────────────────────────────────────
    scale_factor, raw_total_risk = compute_risk_scaling(
        selected, balance, max_risk_pct,
    )

    # ── Step 6: Allocation weights ────────────────────────────────────────────
    weights = compute_allocation_weights(selected)

    # ── Build output ─────────────────────────────────────────────────────────
    selected_trades: List[SelectedTrade] = []
    total_risk = 0.0

    for trade, weight in zip(selected, weights):
        scaled_position = round(trade.position_size * scale_factor, 4)
        scaled_risk = round(trade.risk_amount * scale_factor, 4)
        total_risk += scaled_risk

        category = get_asset_category(trade.symbol)

        selected_trades.append(SelectedTrade(
            symbol=trade.symbol,
            signal=trade.signal,
            score=getattr(trade, "confidence", 0.0),  # use confidence as score proxy
            confidence=trade.confidence,
            position_size=scaled_position,
            risk_amount=scaled_risk,
            stop_loss_distance=trade.stop_loss_distance,
            allocation_weight=weight,
            regime=trade.regime,
            category=category,
        ))

    total_risk = round(total_risk, 4)
    remaining = round(max_allowed_risk - total_risk, 4)

    summary = PortfolioSummary(
        total_positions=len(selected_trades),
        total_risk=total_risk,
        max_allowed_risk=round(max_allowed_risk, 4),
        remaining_capacity=max(0.0, remaining),
        scale_factor=scale_factor,
    )

    logger.info(
        "[Portfolio] Allocated %d trades | risk=$%.2f / $%.2f | scale=%.4f",
        len(selected_trades), total_risk, max_allowed_risk, scale_factor,
    )

    return PortfolioDecision(
        selected_trades=selected_trades,
        portfolio=summary,
    )


def _empty_portfolio(max_allowed_risk: float) -> PortfolioDecision:
    """Return an empty portfolio when no trades qualify."""
    return PortfolioDecision(
        selected_trades=[],
        portfolio=PortfolioSummary(
            total_positions=0,
            total_risk=0.0,
            max_allowed_risk=round(max_allowed_risk, 4),
            remaining_capacity=round(max_allowed_risk, 4),
            scale_factor=1.0,
        ),
    )
