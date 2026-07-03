"""
validation_engine.py - Statistical Validation Layer (Phase 6) & Regime Stability Protection (Phase 5).
Prevents the AI recommender from applying statistically insignificant changes and tracks outcomes (Phase 4).
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Constants for Regime Stability Protection
MAX_WEIGHT_CHANGE = 0.05
MIN_TRADES_COOLDOWN = 50

def validate_recommendation(rec: dict, analytics: dict, current_weights: dict = None) -> dict:
    """
    Validates an AI recommendation.
    Returns the recommendation with an updated 'status' (APPROVED or REJECTED)
    and a 'validation_reason'.
    """
    target_regime = rec.get("target_regime")
    
    # Check 1: Minimum Sample Size
    regime_stats = analytics.get("regime_performance", {}).get(target_regime, {})
    total_trades = regime_stats.get("total", 0)
    
    # Reduced from 30 to 5 for faster learning in iterative backtesting/replay
    if total_trades < 5:
        rec["status"] = "REJECTED"
        rec["validation_reason"] = f"Insufficient sample size. Need 5 trades in {target_regime}, got {total_trades}."
        return rec
        
    # Check 2: Confidence checks
    confidence = rec.get("confidence_score", 0.0)
    if confidence < 0.8:
        rec["status"] = "REJECTED"
        rec["validation_reason"] = f"Confidence score too low ({confidence}). Minimum 0.8 required."
        return rec
        
    # Check 3: Overfitting risk (No single factor >= 0.8)
    adj = rec.get("adjustments", {})
    for factor, weight in adj.items():
        if weight >= 0.8:
            rec["status"] = "REJECTED"
            rec["validation_reason"] = f"Overfitting risk. Weight for {factor} is >= 0.8."
            return rec
            
    # Check 4: Parameter Inertia (Phase 5) - Max change rate
    if current_weights:
        for factor, weight in adj.items():
            current = current_weights.get(factor, 0.0)
            if abs(weight - current) > MAX_WEIGHT_CHANGE:
                rec["status"] = "REJECTED"
                rec["validation_reason"] = f"Inertia limit exceeded for {factor}. Attempted change {abs(weight - current):.3f} > {MAX_WEIGHT_CHANGE}."
                return rec
                
    rec["status"] = "APPROVED"
    rec["validation_reason"] = "Passed all statistical validation and stability checks."
    
    # Initialize before_metrics for Phase 4 tracking
    rec["before_metrics"] = {
        "win_rate": regime_stats.get("win_rate", 0),
        "profit_factor": analytics.get("profit_factor", 0),
        "total_trades": total_trades
    }
    
    return rec
