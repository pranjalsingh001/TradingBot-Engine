"""
slippage_model.py — Realistic slippage simulation (Phase G.1).
"""


def compute_slippage(
    direction: str,
    entry_price: float,
    position_size_usd: float,
    atr_5m: float,
    regime: str,
    candle_type: str = "normal",
) -> float:
    """Return adjusted fill price (worse than requested)."""
    if entry_price <= 0:
        return entry_price

    base_bps = 2  # 2 basis points baseline

    # Volatility adjustment
    vol_adj = (atr_5m / entry_price) * 100 if entry_price > 0 else 0

    # Size adjustment
    size_adj = min(position_size_usd / 100_000, 1.0) * 3

    # Regime multiplier
    if regime == "HIGH_VOLATILITY":
        mult = 3.0
    elif candle_type == "breakout":
        mult = 2.0
    else:
        mult = 1.0

    total_bps = (base_bps + vol_adj + size_adj) * mult
    slippage_price = entry_price * (total_bps / 10_000)

    if direction == "LONG":
        return round(entry_price + slippage_price, 4)
    else:
        return round(entry_price - slippage_price, 4)
