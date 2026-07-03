"""
trade_quality_evaluator.py — Trade quality assessment (Phase E.3).
"""
from app.core.models import TradeQuality


def evaluate_trade_quality(trades: list) -> TradeQuality:
    """Assess quality of recent trades: confidence, frequency, MFE/MAE."""
    if not trades:
        return TradeQuality()

    total = len(trades)
    confidences = [t.get("confidence", 0.5) for t in trades]
    avg_conf = sum(confidences) / total
    low_conf = sum(1 for c in confidences if c < 0.55) / total

    hold_times = [t.get("hold_time_min", 0) for t in trades]
    avg_hold = sum(hold_times) / total if total > 0 else 0

    # Frequency: estimate from timestamps if available
    freq = total  # per evaluation window (default 1 day)

    mfes = [t.get("mfe", 0) for t in trades]
    maes = [t.get("mae", 0) for t in trades]
    avg_mfe = sum(mfes) / total if total > 0 else 0
    avg_mae = sum(maes) / total if total > 0 else 0
    ratio = avg_mfe / avg_mae if avg_mae > 0 else 1.0

    return TradeQuality(
        avg_confidence=round(avg_conf, 3),
        low_confidence_rate=round(low_conf, 3),
        trade_frequency_per_day=round(freq, 1),
        avg_hold_time_minutes=round(avg_hold, 1),
        avg_mfe=round(avg_mfe, 4),
        avg_mae=round(avg_mae, 4),
        mfe_mae_ratio=round(ratio, 3),
    )
