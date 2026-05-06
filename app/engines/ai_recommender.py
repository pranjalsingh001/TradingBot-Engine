"""
ai_recommender.py - Controlled AI Recommendation Layer (Phase 5).
Deterministic, statistical AI stub that suggests weight adjustments.
"""
import uuid
import logging
from datetime import datetime, timezone
from app.core.db import save_recommendation

logger = logging.getLogger(__name__)

async def generate_recommendations(analytics: dict) -> list:
    """Analyze historical performance and recommend config adjustments."""
    if "error" in analytics:
        return []
        
    recommendations = []
    
    # Example Rule 1: SIDEWAYS underperforming
    regime_perf = analytics.get("regime_performance", {})
    if "SIDEWAYS" in regime_perf:
        sideways = regime_perf["SIDEWAYS"]
        if sideways["total"] >= 10 and sideways["win_rate"] < 0.40:
            rec = {
                "recommendation_id": str(uuid.uuid4()),
                "target_regime": "SIDEWAYS",
                "adjustments": {
                    "momentum": 0.6,
                    "trend": 0.1,
                    "trend_strength": 0.1,
                    "volatility": 0.2
                },
                "reason": f"SIDEWAYS win rate is {sideways['win_rate']*100:.1f}%. Increasing momentum weight.",
                "confidence_score": 0.85,
                "status": "PENDING",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            recommendations.append(rec)
            await save_recommendation(rec)
            
    # Example Rule 2: TRENDING underperforming
    if "TRENDING" in regime_perf:
        trending = regime_perf["TRENDING"]
        if trending["total"] >= 10 and trending["win_rate"] < 0.40:
            rec = {
                "recommendation_id": str(uuid.uuid4()),
                "target_regime": "TRENDING",
                "adjustments": {
                    "momentum": 0.1,
                    "trend": 0.5,
                    "trend_strength": 0.3,
                    "volatility": 0.1
                },
                "reason": f"TRENDING win rate is {trending['win_rate']*100:.1f}%. Increasing trend weight.",
                "confidence_score": 0.90,
                "status": "PENDING",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            recommendations.append(rec)
            await save_recommendation(rec)

    return recommendations
