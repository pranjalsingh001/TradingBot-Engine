"""
equity_curve.py — Equity curve analytics (Phase G.4).
"""
import numpy as np
from app.core.models import EquityCurveMetrics


def compute_equity_curve_metrics(
    trade_pnls: list,
    starting_equity: float = 10_000,
    risk_free_rate: float = 0.045,
) -> EquityCurveMetrics:
    """Compute comprehensive metrics from a list of trade net P&Ls."""
    if not trade_pnls:
        return EquityCurveMetrics()

    pnls = np.array(trade_pnls, dtype=float)
    n = len(pnls)

    # Build equity curve
    equity = np.concatenate([[starting_equity], starting_equity + np.cumsum(pnls)])

    # Win/loss stats
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / n if n > 0 else 0

    avg_win = float(wins.mean()) if win_count > 0 else 0
    avg_loss = float(abs(losses.mean())) if loss_count > 0 else 0
    avg_win_r = avg_win / avg_loss if avg_loss > 0 else 0
    avg_loss_r = 1.0  # normalized
    expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r) if avg_loss > 0 else 0

    # Profit factor
    gross_profit = float(wins.sum()) if win_count > 0 else 0
    gross_loss = float(abs(losses.sum())) if loss_count > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

    # Drawdown
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / np.where(peak > 0, peak, 1)
    max_dd = float(dd.max())

    # Drawdown duration
    in_dd = dd > 0
    max_dd_dur = 0
    curr_dur = 0
    for d in in_dd:
        if d:
            curr_dur += 1
            max_dd_dur = max(max_dd_dur, curr_dur)
        else:
            curr_dur = 0

    # Daily returns (approximate: each trade = 1 day)
    returns = np.diff(equity) / equity[:-1]
    returns = returns[np.isfinite(returns)]

    # Sharpe
    if len(returns) > 1 and returns.std() > 0:
        ann_ret = float(returns.mean()) * 252
        ann_std = float(returns.std()) * np.sqrt(252)
        sharpe = (ann_ret - risk_free_rate) / ann_std
    else:
        sharpe = 0

    # Sortino
    down_ret = returns[returns < 0]
    if len(down_ret) > 1 and down_ret.std() > 0:
        sortino = (float(returns.mean()) * 252 - risk_free_rate) / (float(down_ret.std()) * np.sqrt(252))
    else:
        sortino = 0

    # Calmar
    ann_return = float(returns.mean()) * 252 if len(returns) > 0 else 0
    calmar = ann_return / max_dd if max_dd > 0 else 0

    # Recovery factor
    total_profit = float(pnls.sum())
    max_dd_abs = float((peak - equity).max())
    recovery = total_profit / max_dd_abs if max_dd_abs > 0 else 0

    # Streaks
    longest_win = longest_loss = curr_w = curr_l = 0
    for p in pnls:
        if p > 0:
            curr_w += 1; curr_l = 0; longest_win = max(longest_win, curr_w)
        elif p < 0:
            curr_l += 1; curr_w = 0; longest_loss = max(longest_loss, curr_l)
        else:
            curr_w = 0; curr_l = 0

    return EquityCurveMetrics(
        sharpe_ratio=round(sharpe, 3), sortino_ratio=round(sortino, 3),
        calmar_ratio=round(calmar, 3), max_drawdown_pct=round(max_dd, 4),
        max_drawdown_duration_days=max_dd_dur, recovery_factor=round(recovery, 3),
        profit_factor=round(profit_factor, 3), win_rate=round(win_rate, 3),
        avg_win_R=round(avg_win_r, 3), avg_loss_R=round(avg_loss_r, 3),
        expectancy_R=round(expectancy, 3), total_trades=n,
        avg_trades_per_day=round(n / max(1, n / 5), 2),
        longest_win_streak=longest_win, longest_loss_streak=longest_loss,
    )
