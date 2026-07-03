"""
structure.py — Support & Resistance mapping (Phase D.6).
"""
import numpy as np
import pandas as pd
from app.core.models import StructureLevels


def compute_structure_levels(
    candles_15m: pd.DataFrame,
    tolerance_atr: float = 0.5,
    min_touches: int = 2,
    lookback: int = 100,
) -> StructureLevels:
    if candles_15m.empty or len(candles_15m) < 10:
        return StructureLevels()

    df = candles_15m.iloc[-lookback:] if len(candles_15m) >= lookback else candles_15m
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    close = df["close"].astype(float).values
    current_price = close[-1]

    # ATR for tolerance
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr)) if len(tr) > 0 else 1.0
    tol = atr * tolerance_atr

    # Find swing highs and lows (2-bar on each side)
    swing_highs = []
    swing_lows = []
    for i in range(2, len(high) - 2):
        if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
            swing_highs.append(high[i])
        if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
            swing_lows.append(low[i])

    # Cluster nearby levels
    resistance = _cluster_levels(swing_highs, tol, min_touches)
    support = _cluster_levels(swing_lows, tol, min_touches)

    # Sort relative to current price
    resistance = sorted([r for r in resistance if r > current_price])
    support = sorted([s for s in support if s < current_price], reverse=True)

    nr = resistance[0] if resistance else current_price * 1.1
    ns = support[0] if support else current_price * 0.9

    return StructureLevels(
        resistance_levels=[round(r, 2) for r in resistance[:5]],
        support_levels=[round(s, 2) for s in support[:5]],
        nearest_resistance=round(nr, 2),
        nearest_support=round(ns, 2),
        distance_to_resistance_atr=round((nr - current_price) / atr, 2) if atr > 0 else float('inf'),
        distance_to_support_atr=round((current_price - ns) / atr, 2) if atr > 0 else float('inf'),
    )


def _cluster_levels(prices: list, tolerance: float, min_touches: int) -> list:
    """Cluster nearby prices and return levels with >= min_touches."""
    if not prices:
        return []
    prices = sorted(prices)
    clusters = []
    current_cluster = [prices[0]]

    for p in prices[1:]:
        if abs(p - current_cluster[-1]) < tolerance:
            current_cluster.append(p)
        else:
            if len(current_cluster) >= min_touches:
                clusters.append(float(np.mean(current_cluster)))
            current_cluster = [p]
    if len(current_cluster) >= min_touches:
        clusters.append(float(np.mean(current_cluster)))

    return clusters
