"""
statistical_guard.py — Sample size, inertia, stability checks (Phase F.1-F.4).
"""

MINIMUM_SAMPLES = {
    "strategy_activation": 30,
    "strategy_deactivation": 30,
    "regime_parameter": 20,
    "threshold": 15,
    "risk_reduction": 5,
}

INERTIA_RULES = {
    "indicator_weight": 0.05,
    "confidence_threshold": 0.05,
    "position_size_scalar": 0.10,
    "sl_multiplier": 0.10,
    "base_risk_pct": 0.20,
}


def has_sufficient_sample(trade_count: int, change_type: str) -> bool:
    """Check if we have enough trades to justify a change."""
    minimum = MINIMUM_SAMPLES.get(change_type, 30)
    return trade_count >= minimum


def is_within_inertia(parameter: str, current_value: float, proposed_value: float) -> tuple:
    """Check if proposed change is within weekly inertia limits.
    Returns (within_limit: bool, capped_value: float).
    """
    if current_value == 0:
        return True, proposed_value

    max_change_pct = INERTIA_RULES.get(parameter, 0.05)
    actual_change_pct = abs(proposed_value - current_value) / abs(current_value)

    if actual_change_pct <= max_change_pct:
        return True, proposed_value

    # Cap to inertia limit
    direction = 1 if proposed_value > current_value else -1
    capped = current_value * (1 + direction * max_change_pct)
    return False, round(capped, 6)


def is_improvement_stable(
    metric_history: list,
    proposed_direction: str = "increase",
    min_improvement_days: int = 5,
) -> bool:
    """Check if improvement has been consistent for min_improvement_days."""
    if len(metric_history) < min_improvement_days:
        return False
    recent = metric_history[-min_improvement_days:]
    if proposed_direction == "increase":
        return all(recent[i] <= recent[i+1] for i in range(len(recent)-1))
    else:
        return all(recent[i] >= recent[i+1] for i in range(len(recent)-1))
