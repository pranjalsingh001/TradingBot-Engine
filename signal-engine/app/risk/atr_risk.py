"""
atr_risk.py — ATR-based SL/TP computation (Phase C.1).
SL and TP are dynamically computed per regime using structural anchors and ATR buffers.
"""

def compute_sl_tp(signal, atr_5m: float, regime: str) -> tuple:
    """
    Compute regime-adjusted SL and TP.
    Prioritizes the strategy's structural raw_sl, adding a small ATR buffer to protect against wicks.
    If raw_sl is missing, falls back to pure ATR distance.
    """
    multipliers = {
        "TRENDING":       (0.5, 2.0), # buffer_mult, rr
        "SIDEWAYS":       (0.2, 1.2),
        "BREAKOUT":       (1.0, 2.5),
        "HIGH_VOLATILITY": (1.5, 1.5),
    }
    buffer_mult, rr = multipliers.get(regime, (0.5, 2.0))

    if signal.direction == "LONG":
        if signal.raw_sl > 0 and signal.raw_sl < signal.entry_price:
            sl = signal.raw_sl - (atr_5m * buffer_mult)
        else:
            sl = signal.entry_price - (atr_5m * 1.5)
            
        tp = signal.entry_price + (signal.entry_price - sl) * rr
        
    elif signal.direction == "SHORT":
        if signal.raw_sl > 0 and signal.raw_sl > signal.entry_price:
            sl = signal.raw_sl + (atr_5m * buffer_mult)
        else:
            sl = signal.entry_price + (atr_5m * 1.5)
            
        tp = signal.entry_price - (sl - signal.entry_price) * rr
    else:
        return signal.entry_price, signal.entry_price

    return round(sl, 2), round(tp, 2)

