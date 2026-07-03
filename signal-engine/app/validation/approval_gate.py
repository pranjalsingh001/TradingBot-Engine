"""
approval_gate.py — Human/auto approval logic (Phase F.5).
"""
import logging
from app.validation.statistical_guard import has_sufficient_sample, is_within_inertia, is_improvement_stable

logger = logging.getLogger(__name__)


def evaluate_recommendation(rec, walk_forward_frozen: bool = False, applied_last_7_days: int = 0) -> dict:
    """
    Evaluate whether a recommendation can be auto-approved or requires manual review.
    Returns {"action": "AUTO_APPROVE" | "MANUAL_REQUIRED" | "REJECT" | "CAP", "reason": str, "capped_value": optional}
    """
    proposed = rec.proposed_change if hasattr(rec, 'proposed_change') else rec.get("proposed_change", {})
    evidence = rec.evidence if hasattr(rec, 'evidence') else rec.get("evidence", {})
    priority = rec.priority if hasattr(rec, 'priority') else rec.get("priority", "MEDIUM")

    # Walk-forward freeze
    if walk_forward_frozen:
        return {"action": "FROZEN", "reason": "Walk-forward test window in progress"}

    # Determine change type
    param = proposed.get("parameter", "")
    if "is_active" in param:
        change_type = "strategy_deactivation" if not proposed.get("proposed_value", True) else "strategy_activation"
    elif "risk" in param.lower():
        change_type = "risk_reduction"
    elif "threshold" in param.lower() or "confidence" in param.lower():
        change_type = "threshold"
    else:
        change_type = "regime_parameter"

    # Manual approval required conditions (check BEFORE inertia/sample)
    if priority == "CRITICAL":
        return {"action": "MANUAL_REQUIRED", "reason": "CRITICAL priority requires human confirmation"}
    if "is_active" in param:
        return {"action": "MANUAL_REQUIRED", "reason": "Strategy activation/deactivation requires human confirmation"}
    if "base_risk_pct" in param:
        return {"action": "MANUAL_REQUIRED", "reason": "Risk parameter change requires human confirmation"}
    if applied_last_7_days >= 3:
        return {"action": "MANUAL_REQUIRED", "reason": f"3+ recommendations applied in 7 days ({applied_last_7_days})"}

    # Sample size check
    trade_count = evidence.get("trade_count", 0)
    if trade_count > 0 and not has_sufficient_sample(trade_count, change_type):
        return {"action": "REJECT", "reason": f"Insufficient sample: {trade_count} trades (need {change_type})"}

    # Inertia check
    current = proposed.get("current_value")
    proposed_val = proposed.get("proposed_value")
    if isinstance(current, (int, float)) and isinstance(proposed_val, (int, float)) and current != 0:
        within, capped = is_within_inertia(param.split(".")[-1], current, proposed_val)
        if not within:
            return {"action": "CAP", "reason": f"Inertia limit: capped to {capped}", "capped_value": capped}

    # Auto-approve
    return {"action": "AUTO_APPROVE", "reason": "All validation checks passed"}
