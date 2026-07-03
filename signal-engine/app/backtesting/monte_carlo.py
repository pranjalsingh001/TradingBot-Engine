"""
monte_carlo.py — Monte Carlo stress testing (Phase G.3).
"""
import numpy as np
from app.core.models import MonteCarloResult


def run_monte_carlo(
    trade_results: list,
    n_simulations: int = 1000,
    starting_equity: float = 10_000,
) -> MonteCarloResult:
    """Run Monte Carlo simulation by shuffling trade outcomes."""
    if not trade_results or len(trade_results) < 5:
        return MonteCarloResult(median_final_equity=starting_equity, p5_final_equity=starting_equity, p95_final_equity=starting_equity)

    results = np.array(trade_results, dtype=float)
    n_trades = len(results)

    final_equities = []
    max_drawdowns = []
    sharpes = []

    rng = np.random.default_rng(42)

    for _ in range(n_simulations):
        # Bootstrap resample
        shuffled = rng.choice(results, size=n_trades, replace=True)

        # Add slippage noise
        noise = rng.normal(0, 0.0003, size=n_trades)
        shuffled = shuffled * (1 + noise)

        # Skip ~2% of trades (execution failure)
        mask = rng.random(n_trades) > 0.02
        shuffled = shuffled[mask]

        if len(shuffled) == 0:
            final_equities.append(starting_equity)
            max_drawdowns.append(0)
            sharpes.append(0)
            continue

        # Equity curve
        equity = starting_equity
        curve = [equity]
        for pnl in shuffled:
            equity += pnl
            curve.append(equity)

        curve = np.array(curve)
        final_equities.append(curve[-1])

        # Max drawdown
        peak = np.maximum.accumulate(curve)
        dd = (peak - curve) / np.where(peak > 0, peak, 1)
        max_drawdowns.append(float(dd.max()))

        # Sharpe (simplified)
        if len(shuffled) > 1:
            daily_ret = np.diff(curve) / curve[:-1]
            if daily_ret.std() > 0:
                sharpes.append(float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)))
            else:
                sharpes.append(0)
        else:
            sharpes.append(0)

    fe = np.array(final_equities)
    md = np.array(max_drawdowns)
    ruin = float(np.mean(fe < starting_equity * 0.5))

    return MonteCarloResult(
        median_final_equity=round(float(np.median(fe)), 2),
        p5_final_equity=round(float(np.percentile(fe, 5)), 2),
        p95_final_equity=round(float(np.percentile(fe, 95)), 2),
        median_max_drawdown=round(float(np.median(md)), 4),
        p95_max_drawdown=round(float(np.percentile(md, 95)), 4),
        ruin_probability=round(ruin, 4),
        sharpe_distribution=[round(float(s), 3) for s in sharpes[:100]],
    )
