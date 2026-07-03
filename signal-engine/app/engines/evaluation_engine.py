"""
evaluation_engine.py — Quantitative strategy evaluation framework.

Takes backtester output (trades + equity curve) and produces
comprehensive performance metrics, distribution analysis,
consistency checks, and rule-based interpretation.

Single responsibility: evaluation only.
No DB calls. No HTTP. No randomness.
Does NOT modify backtester logic.
"""

import logging
import math
from typing import List, Tuple

from app.core.schemas import (
    EvalSummary, EvalDistribution, EvalConsistency,
    EvalInterpretation, EvaluationResult,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
ANNUALIZATION_FACTOR = 252  # trading days per year
CONCENTRATION_THRESHOLD = 0.50  # top 10% contributing > 50% = concentrated


# ── 2.1 Total Return ─────────────────────────────────────────────────────────

def compute_total_return(equity_curve: List[float]) -> float:
    """Total return as percentage."""
    if len(equity_curve) < 2 or equity_curve[0] == 0:
        return 0.0
    return round(
        ((equity_curve[-1] - equity_curve[0]) / equity_curve[0]) * 100, 4
    )


# ── 2.2 Win Rate ─────────────────────────────────────────────────────────────

def compute_win_rate(profits: List[float]) -> float:
    """Fraction of profitable trades."""
    if not profits:
        return 0.0
    winners = sum(1 for p in profits if p > 0)
    return round(winners / len(profits), 4)


# ── 2.3 Profit Factor ────────────────────────────────────────────────────────

def compute_profit_factor(profits: List[float]) -> float:
    """
    Total profit / total loss.

    Edge cases:
        - No losses → returns inf-safe large value (999.99)
        - No wins → 0.0
        - No trades → 0.0
    """
    if not profits:
        return 0.0
    total_profit = sum(p for p in profits if p > 0)
    total_loss = abs(sum(p for p in profits if p < 0))

    if total_loss == 0:
        return 999.99 if total_profit > 0 else 0.0

    return round(total_profit / total_loss, 4)


# ── 2.4 Expectancy ───────────────────────────────────────────────────────────

def compute_expectancy(profits: List[float]) -> float:
    """
    Expected value per trade.

    expectancy = (avg_win × win_rate) - (avg_loss × loss_rate)
    """
    if not profits:
        return 0.0

    winners = [p for p in profits if p > 0]
    losers = [p for p in profits if p < 0]

    win_rate = len(winners) / len(profits) if profits else 0
    loss_rate = len(losers) / len(profits) if profits else 0

    avg_win = sum(winners) / len(winners) if winners else 0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 0

    return round((avg_win * win_rate) - (avg_loss * loss_rate), 4)


# ── 2.5 Max Drawdown ─────────────────────────────────────────────────────────

def compute_max_drawdown(equity_curve: List[float]) -> float:
    """
    Peak-to-trough decline as percentage.

    Iterates through equity curve tracking the running peak
    and the maximum percentage decline from that peak.
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)

    return round(max_dd * 100, 4)  # as percentage


# ── 2.6 Sharpe Ratio ─────────────────────────────────────────────────────────

def compute_sharpe_ratio(equity_curve: List[float]) -> float:
    """
    Simplified annualized Sharpe ratio.

    sharpe = (mean_return / std_dev) × sqrt(252)
    """
    if len(equity_curve) < 3:
        return 0.0

    # Compute period returns
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            r = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            returns.append(r)

    if not returns:
        return 0.0

    mean_return = sum(returns) / len(returns)

    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    sharpe = (mean_return / std_dev) * math.sqrt(ANNUALIZATION_FACTOR)
    return round(sharpe, 4)


# ── 3. Trade Distribution ────────────────────────────────────────────────────

def compute_distribution(profits: List[float]) -> dict:
    """Compute trade distribution metrics."""
    winners = [p for p in profits if p > 0]
    losers = [p for p in profits if p < 0]

    avg_win = round(sum(winners) / len(winners), 4) if winners else 0.0
    avg_loss = round(sum(losers) / len(losers), 4) if losers else 0.0
    largest_win = round(max(winners), 4) if winners else 0.0
    largest_loss = round(min(losers), 4) if losers else 0.0

    max_consec_wins = _max_consecutive(profits, positive=True)
    max_consec_losses = _max_consecutive(profits, positive=False)

    return {
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
    }


def _max_consecutive(profits: List[float], positive: bool) -> int:
    """Count max consecutive wins or losses."""
    max_streak = 0
    current_streak = 0

    for p in profits:
        if (positive and p > 0) or (not positive and p < 0):
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return max_streak


# ── 4. Consistency ───────────────────────────────────────────────────────────

def compute_consistency(profits: List[float]) -> dict:
    """
    Check if profits are distributed or concentrated.

    Measures what percentage of total profit comes from the top 10% of trades.
    """
    if not profits:
        return {"top_10_pct_contribution": 0.0, "is_concentrated": False}

    total_profit = sum(p for p in profits if p > 0)
    if total_profit <= 0:
        return {"top_10_pct_contribution": 0.0, "is_concentrated": False}

    # Sort profits descending
    sorted_profits = sorted([p for p in profits if p > 0], reverse=True)

    # Top 10% of winning trades
    top_count = max(1, len(sorted_profits) // 10)
    top_profit = sum(sorted_profits[:top_count])

    contribution = round(top_profit / total_profit, 4)

    return {
        "top_10_pct_contribution": contribution,
        "is_concentrated": contribution > CONCENTRATION_THRESHOLD,
    }


# ── 6. Interpretation ────────────────────────────────────────────────────────

def compute_interpretation(
    total_return: float,
    win_rate: float,
    profit_factor: float,
    expectancy: float,
    max_drawdown: float,
    sharpe: float,
) -> dict:
    """
    Rule-based strategy grading.

    Returns a letter grade (A–F) and a list of flags.
    """
    flags: List[str] = []
    score = 0

    # Drawdown assessment
    if max_drawdown > 20:
        flags.append("⚠ High risk: max drawdown exceeds 20%")
    elif max_drawdown > 10:
        flags.append("⚡ Moderate risk: drawdown between 10–20%")
    else:
        score += 2
        flags.append("✅ Drawdown under control (<10%)")

    # Profit factor
    if profit_factor < 1.0:
        flags.append("❌ Losing system: profit factor < 1.0")
    elif profit_factor < 1.2:
        flags.append("⚠ Weak edge: profit factor 1.0–1.2")
        score += 1
    elif profit_factor < 2.0:
        flags.append("✅ Decent edge: profit factor 1.2–2.0")
        score += 2
    else:
        flags.append("🔥 Strong edge: profit factor > 2.0")
        score += 3

    # Sharpe ratio
    if sharpe < 0:
        flags.append("❌ Negative risk-adjusted returns")
    elif sharpe < 1.0:
        flags.append("⚠ Low risk-adjusted returns (Sharpe < 1)")
        score += 1
    elif sharpe < 2.0:
        flags.append("✅ Good risk-adjusted returns (Sharpe 1–2)")
        score += 2
    else:
        flags.append("🔥 Excellent risk-adjusted returns (Sharpe > 2)")
        score += 3

    # Win rate
    if win_rate > 0.55:
        score += 1
    if win_rate < 0.35:
        flags.append("⚠ Low win rate (<35%)")

    # Expectancy
    if expectancy > 0:
        score += 1
        flags.append(f"✅ Positive expectancy: {expectancy:.2f} per trade")
    else:
        flags.append(f"❌ Negative expectancy: {expectancy:.2f} per trade")

    # Total return
    if total_return > 0:
        score += 1

    # Grade
    if score >= 9:
        grade = "A"
    elif score >= 7:
        grade = "B"
    elif score >= 5:
        grade = "C"
    elif score >= 3:
        grade = "D"
    else:
        grade = "F"

    return {"grade": grade, "flags": flags}


# ── Core engine ──────────────────────────────────────────────────────────────

def evaluate_backtest(
    trades: List[dict],
    equity_curve: List[float],
) -> EvaluationResult:
    """
    Core evaluation function.

    Parameters
    ----------
    trades       : list of trade dicts, each must have a 'profit' key
    equity_curve : list of account values over time

    Returns
    -------
    EvaluationResult with summary, distribution, consistency, interpretation
    """
    profits = [float(t.get("profit", 0)) for t in trades]

    # ── Summary metrics ──────────────────────────────────────────────────────
    total_return = compute_total_return(equity_curve)
    win_rate = compute_win_rate(profits)
    profit_factor = compute_profit_factor(profits)
    expectancy = compute_expectancy(profits)
    max_drawdown = compute_max_drawdown(equity_curve)
    sharpe = compute_sharpe_ratio(equity_curve)

    summary = EvalSummary(
        total_trades=len(trades),
        total_return_pct=total_return,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=sharpe,
    )

    # ── Distribution ─────────────────────────────────────────────────────────
    dist = compute_distribution(profits)
    distribution = EvalDistribution(**dist)

    # ── Consistency ──────────────────────────────────────────────────────────
    cons = compute_consistency(profits)
    consistency = EvalConsistency(**cons)

    # ── Interpretation ───────────────────────────────────────────────────────
    interp = compute_interpretation(
        total_return, win_rate, profit_factor,
        expectancy, max_drawdown, sharpe,
    )
    interpretation = EvalInterpretation(**interp)

    logger.info(
        "[Eval] %d trades | return=%.2f%% | win_rate=%.2f | "
        "PF=%.2f | sharpe=%.2f | DD=%.2f%% | grade=%s",
        len(trades), total_return, win_rate,
        profit_factor, sharpe, max_drawdown, interp["grade"],
    )

    return EvaluationResult(
        summary=summary,
        distribution=distribution,
        consistency=consistency,
        interpretation=interpretation,
    )
