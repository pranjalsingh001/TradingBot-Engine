"""
strategy_evaluator.py — Strategy health scoring (Phase E.1).
Scores each strategy's health on a rolling basis.
"""
from app.core.models import StrategyHealth


def evaluate_strategy_health(
    strategy_id: str,
    trades: list,
    evaluation_period: str = "last_20_trades",
) -> StrategyHealth:
    """Compute health score for a strategy from its recent trades."""
    if not trades:
        return StrategyHealth(strategy_id=strategy_id, evaluation_period=evaluation_period)

    total = len(trades)
    wins = sum(1 for t in trades if t.get("result") == "WIN")
    losses = sum(1 for t in trades if t.get("result") == "LOSS")
    win_rate = wins / total if total > 0 else 0

    # Expectancy
    win_pnls = [t.get("r_multiple", 0) for t in trades if t.get("result") == "WIN"]
    loss_pnls = [abs(t.get("r_multiple", 0)) for t in trades if t.get("result") == "LOSS"]
    avg_win_r = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss_r = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
    expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)
    avg_rr = avg_win_r / avg_loss_r if avg_loss_r > 0 else 0

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades:
        if t.get("result") == "LOSS":
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    # Drawdown in period
    equity = 0
    peak = 0
    max_dd = 0
    for t in trades:
        equity += t.get("net_pnl", 0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Health score (0-100)
    wr_score = min(win_rate / 0.55, 1.0) * 30
    exp_score = min(max(expectancy / 0.5, 0), 1.0) * 30
    con_score = max(1 - (max_consec / 7), 0) * 20
    dd_score = max(1 - (max_dd / 0.10), 0) * 20
    health_score = round(wr_score + exp_score + con_score + dd_score, 1)

    if health_score >= 60:
        status = "HEALTHY"
        rec = None
    elif health_score >= 35:
        status = "DEGRADING"
        rec = f"Reduce {strategy_id} position sizes by 25% for next 15 trades"
    else:
        status = "CRITICAL"
        rec = f"Deactivate {strategy_id} immediately"

    return StrategyHealth(
        strategy_id=strategy_id, evaluation_period=evaluation_period,
        trade_count=total, win_rate=round(win_rate, 3), expectancy=round(expectancy, 3),
        avg_rr=round(avg_rr, 2), max_consecutive_losses=max_consec,
        drawdown_in_period=round(max_dd, 4), health_score=health_score,
        health_status=status, recommendation=rec,
    )
