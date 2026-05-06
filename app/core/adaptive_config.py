"""
adaptive_config.py - Adaptive Config Engine (Phase 7).
Loads approved configurations and dynamically overrides default weights.
"""
import logging
from app.core.db import get_db

logger = logging.getLogger(__name__)

# In-memory cache of approved weights
_adaptive_weights = {}

async def load_approved_profiles() -> None:
    """Fetch the latest approved recommendations for each regime and cache them."""
    collection = get_db()["recommendations"]
    
    try:
        # We want the most recent approved recommendation per regime
        cursor = collection.find({"status": "APPROVED"}).sort("timestamp", -1)
        recs = await cursor.to_list(length=100)
        
        loaded_regimes = set()
        for rec in recs:
            regime = rec.get("target_regime")
            if regime and regime not in loaded_regimes:
                _adaptive_weights[regime] = rec.get("adjustments", {})
                loaded_regimes.add(regime)
                logger.info("[Adaptive Config] Loaded custom profile for %s", regime)
    except Exception as e:
        logger.error("[Adaptive Config] Failed to load profiles: %s", e)

def apply_adaptive_weights(regime: str, default_weights: dict) -> dict:
    """Apply adaptive weights if an approved profile exists for the regime."""
    if regime in _adaptive_weights:
        return _adaptive_weights[regime].copy()
    return default_weights.copy()
