"""
position_sizer.py — Dynamic position sizing (Phase C.2).
Risk a fixed % of equity, adjusted by volatility and confidence.
"""

def compute_position_size(
    signal, sl: float, snapshot, portfolio,
    base_risk_pct: float = 1.0,
) -> tuple:
    """
    Compute position size and dollar risk.
    Returns (quantity, dollar_risk).
    """
    entry = signal.entry_price
    if entry <= 0 or sl == entry:
        return 0.0, 0.0

    stop_distance = abs(entry - sl)
    if stop_distance <= 0:
        return 0.0, 0.0

    # Volatility scalar: inverse of atr_pct, clamped
    atr_pct = (snapshot.atr_5m / entry * 100) if entry > 0 else 1.0
    volatility_scalar = max(0.3, min(1.5, 1.0 / atr_pct)) if atr_pct > 0 else 1.0

    # Confidence scalar
    confidence_scalar = max(0.1, signal.confidence)

    adjusted_risk_pct = base_risk_pct * volatility_scalar * confidence_scalar
    dollar_risk = portfolio.equity * (adjusted_risk_pct / 100)

    # Position size from dollar risk and stop distance
    quantity = dollar_risk / stop_distance

    position_size_usd = quantity * entry

    # Regime-based cap (apply AFTER confidence scaling to preserve relative differences)
    max_pct = {"TRENDING": 0.05, "SIDEWAYS": 0.03, "BREAKOUT": 0.04, "HIGH_VOLATILITY": 0.02}
    cap = portfolio.equity * max_pct.get(snapshot.regime, 0.05)
    if position_size_usd > cap:
        quantity = cap / entry
        dollar_risk = quantity * stop_distance
        position_size_usd = cap

    return round(quantity, 6), round(dollar_risk, 2)
