"""
volatility.py — Volatility compression/expansion features (Phase D.3).
"""
import numpy as np
import pandas as pd
from app.core.models import VolatilityFeatures


def compute_volatility_features(candles: pd.DataFrame) -> VolatilityFeatures:
    if candles.empty or len(candles) < 25:
        return VolatilityFeatures()

    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)

    # Bollinger Band width
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_w = (bb_upper - bb_lower) / bb_mid
    bb_w = bb_w.dropna()

    if len(bb_w) < 2:
        return VolatilityFeatures()

    current_bb = float(bb_w.iloc[-1])

    # BB width percentile over last 100 candles
    history = bb_w.iloc[-100:] if len(bb_w) >= 100 else bb_w
    pctile = float((history < current_bb).sum() / len(history) * 100)

    # ATR ratio (current vs 10 periods ago)
    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    atr_ratio = float(atr_s.iloc[-1] / atr_s.iloc[-11]) if len(atr_s) > 11 and atr_s.iloc[-11] > 0 else 1.0

    # Compression detection
    is_compressed = pctile < 20 and atr_ratio < 0.85

    # Compression bars
    comp_bars = 0
    for i in range(1, min(len(history), 50)):
        val = history.iloc[-i]
        h_slice = history.iloc[:-i] if i < len(history) else history
        if len(h_slice) > 0 and float((h_slice < val).sum() / len(h_slice) * 100) < 20:
            comp_bars += 1
        else:
            break

    return VolatilityFeatures(
        bb_width=round(current_bb, 6),
        bb_width_percentile=round(pctile, 2),
        atr_ratio=round(atr_ratio, 4),
        is_compressed=is_compressed,
        compression_bars=comp_bars,
    )
