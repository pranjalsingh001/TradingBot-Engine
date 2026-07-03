"""
risk_escalation.py — Risk escalation detection (Phase E.4).
"""
from datetime import datetime, timezone
from app.core.models import RiskEvent


def detect_risk_events(
    recent_trades: list,
    atr_history: list = None,
    daily_drawdown_pct: float = 0.0,
    max_daily_dd: float = 3.0,
) -> list:
    """Detect emerging risk patterns. Returns list of RiskEvent."""
    events = []

    # 1. Volatility instability
    if atr_history and len(atr_history) >= 8:
        mid = len(atr_history) // 2
        recent_avg = sum(atr_history[mid:]) / len(atr_history[mid:])
        prior_avg = sum(atr_history[:mid]) / mid
        if prior_avg > 0 and recent_avg > 1.5 * prior_avg:
            events.append(RiskEvent(
                "VOLATILITY_INSTABILITY", "HIGH",
                f"ATR increased {(recent_avg/prior_avg-1)*100:.0f}% in recent window",
                recommended_action="Reduce all position sizes by 40% for 6 hours",
            ))

    # 2. Correlated losses
    if recent_trades:
        from collections import Counter
        recent_losses = [t for t in recent_trades[-10:] if t.get("result") == "LOSS"]
        if len(recent_losses) >= 3:
            regime_counts = Counter(t.get("regime") for t in recent_losses)
            for regime, count in regime_counts.items():
                if count >= 3:
                    strat = recent_losses[0].get("strategy_id", "unknown")
                    events.append(RiskEvent(
                        "CORRELATED_LOSSES", "HIGH",
                        f"3+ losses in {regime} regime with {strat}",
                        recommended_action=f"Pause {strat} for 4 hours",
                    ))

    # 3. Drawdown acceleration
    if daily_drawdown_pct > 0.5 * max_daily_dd:
        events.append(RiskEvent(
            "DRAWDOWN_ACCELERATION", "CRITICAL",
            f"Daily drawdown {daily_drawdown_pct:.1f}% exceeds 50% of limit",
            recommended_action="Reduce base_risk_pct to 0.5% for remainder of day",
        ))

    return events
