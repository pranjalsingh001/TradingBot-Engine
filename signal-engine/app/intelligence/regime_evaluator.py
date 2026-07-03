"""
regime_evaluator.py — Regime classifier reliability (Phase E.2).
"""
from app.core.models import RegimeReliability


def evaluate_regime_reliability(
    regime_history: list,
    evaluation_window_hours: int = 24,
    bars_per_hour: float = 4.0,
) -> RegimeReliability:
    """Evaluate regime classifier stability from a list of regime strings."""
    if not regime_history or len(regime_history) < 2:
        return RegimeReliability(evaluation_window_hours=evaluation_window_hours)

    # Count regime changes
    changes = sum(1 for i in range(1, len(regime_history)) if regime_history[i] != regime_history[i-1])

    # Average regime duration (in bars)
    durations = []
    current_dur = 1
    for i in range(1, len(regime_history)):
        if regime_history[i] == regime_history[i-1]:
            current_dur += 1
        else:
            durations.append(current_dur)
            current_dur = 1
    durations.append(current_dur)
    avg_duration = sum(durations) / len(durations)

    # Flip rate
    flip_rate = changes / evaluation_window_hours if evaluation_window_hours > 0 else 0

    # Unstable periods (< 3 bars)
    unstable = sum(1 for d in durations if d < 3)

    # Reliability score
    if avg_duration >= 10:
        base = 1.0
    elif avg_duration >= 5:
        base = 0.7
    else:
        base = 0.3

    if flip_rate > 3:
        base -= 0.3
    if unstable > 5:
        base -= 0.2

    score = max(0, min(1, base))

    return RegimeReliability(
        evaluation_window_hours=evaluation_window_hours,
        total_regime_changes=changes,
        avg_regime_duration_bars=round(avg_duration, 2),
        regime_flip_rate=round(flip_rate, 2),
        unstable_periods=unstable,
        reliability_score=round(score, 3),
        is_reliable=score >= 0.6,
    )
