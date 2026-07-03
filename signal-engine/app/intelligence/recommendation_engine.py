"""
recommendation_engine.py — Aggregates evaluator outputs into recommendations (Phase E.5).
Never modifies live config directly — writes to MongoDB for approval.
"""
from datetime import datetime, timezone
from app.core.models import Recommendation, StrategyHealth, RegimeReliability, TradeQuality, RiskEvent


def generate_recommendations(
    strategy_health: list,
    regime_reliability=None,
    trade_quality=None,
    risk_events: list = None,
) -> list:
    """Aggregate all evaluator outputs into actionable recommendations."""
    recs = []

    # Strategy health recommendations
    for h in strategy_health:
        if not isinstance(h, StrategyHealth):
            continue
        if h.health_status == "CRITICAL":
            recs.append(Recommendation(
                source_evaluator="strategy_evaluator",
                priority="CRITICAL",
                title=f"Deactivate {h.strategy_id}",
                description=f"{h.strategy_id} health score: {h.health_score}/100. Win rate: {h.win_rate:.0%} over {h.trade_count} trades.",
                proposed_change={"parameter": f"strategies.{h.strategy_id}.is_active", "current_value": True, "proposed_value": False},
                evidence={"win_rate": h.win_rate, "expectancy": h.expectancy, "trade_count": h.trade_count, "health_score": h.health_score},
            ))
        elif h.health_status == "DEGRADING":
            recs.append(Recommendation(
                source_evaluator="strategy_evaluator",
                priority="MEDIUM",
                title=f"Reduce {h.strategy_id} exposure",
                description=f"{h.strategy_id} degrading. Health: {h.health_score}/100.",
                proposed_change={"parameter": f"strategies.{h.strategy_id}.confidence_threshold", "current_value": 0.5, "proposed_value": 0.7},
                evidence={"win_rate": h.win_rate, "expectancy": h.expectancy, "health_score": h.health_score},
            ))

    # Regime reliability recommendations
    if regime_reliability and isinstance(regime_reliability, RegimeReliability) and not regime_reliability.is_reliable:
        recs.append(Recommendation(
            source_evaluator="regime_evaluator",
            priority="HIGH",
            title="Regime classifier unstable",
            description=f"Reliability score: {regime_reliability.reliability_score}. Flip rate: {regime_reliability.regime_flip_rate}/hr.",
            proposed_change={"parameter": "regime.adx_threshold", "current_value": 20, "proposed_value": 25},
            evidence={"reliability_score": regime_reliability.reliability_score, "flip_rate": regime_reliability.regime_flip_rate},
        ))

    # Trade quality recommendations
    if trade_quality and isinstance(trade_quality, TradeQuality):
        if trade_quality.low_confidence_rate > 0.3:
            recs.append(Recommendation(
                source_evaluator="trade_quality",
                priority="MEDIUM",
                title="Too many low-confidence trades",
                description=f"{trade_quality.low_confidence_rate:.0%} of trades below 0.55 confidence.",
                proposed_change={"parameter": "min_confidence_threshold", "current_value": 0.5, "proposed_value": 0.6},
                evidence={"low_confidence_rate": trade_quality.low_confidence_rate, "avg_confidence": trade_quality.avg_confidence},
            ))
        if trade_quality.mfe_mae_ratio < 0.8:
            recs.append(Recommendation(
                source_evaluator="trade_quality",
                priority="HIGH",
                title="Poor entry timing",
                description=f"MFE/MAE ratio: {trade_quality.mfe_mae_ratio}. Trades going adverse before favorable.",
                proposed_change={"parameter": "entry_timing_review", "current_value": "none", "proposed_value": "review"},
                evidence={"mfe_mae_ratio": trade_quality.mfe_mae_ratio},
            ))

    # Risk events
    if risk_events:
        for event in risk_events:
            if not isinstance(event, RiskEvent):
                continue
            recs.append(Recommendation(
                source_evaluator="risk_escalation",
                priority=event.severity,
                title=event.event_type.replace("_", " ").title(),
                description=event.description,
                proposed_change={"parameter": "risk_action", "current_value": "none", "proposed_value": event.recommended_action},
                evidence={"event_type": event.event_type},
            ))

    return recs


def deduplicate_recommendations(new_recs: list, existing_recs: list) -> list:
    """Remove duplicate recommendations (same parameter+value within 24h)."""
    existing_keys = set()
    now = datetime.now(timezone.utc)
    for r in existing_recs:
        if r.get("status") == "PENDING":
            created = r.get("created_at")
            if created:
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                elapsed = (now - created).total_seconds()
                if elapsed < 86400:
                    key = (str(r.get("proposed_change", {}).get("parameter")), str(r.get("proposed_change", {}).get("proposed_value")))
                    existing_keys.add(key)

    filtered = []
    for rec in new_recs:
        key = (str(rec.proposed_change.get("parameter")), str(rec.proposed_change.get("proposed_value")))
        if key not in existing_keys:
            filtered.append(rec)

    return filtered
