"""
liquidity.py — Liquidity sweep detection (Phase D.2).
Detects fake breakouts / stop hunts by identifying wick-dominant candles
that pierce structure and close back inside.
"""
import numpy as np
import pandas as pd
from app.core.models import LiquiditySweepResult


def detect_liquidity_sweep(candles: pd.DataFrame, lookback: int = 20) -> LiquiditySweepResult:
    if candles.empty or len(candles) < lookback + 1:
        return LiquiditySweepResult()

    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    opn = candles["open"].astype(float)

    # Structure levels from prior candles (excluding current)
    struct_high = high.iloc[-(lookback+1):-1].max()
    struct_low = low.iloc[-(lookback+1):-1].min()

    # ATR for magnitude
    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.iloc[-15:-1].mean() if len(tr) >= 15 else tr.mean()
    if atr <= 0:
        atr = 1.0

    cur = candles.iloc[-1]
    c_high, c_low = float(cur["high"]), float(cur["low"])
    c_close, c_open = float(cur["close"]), float(cur["open"])
    candle_range = c_high - c_low
    if candle_range <= 0:
        return LiquiditySweepResult()

    body_top = max(c_open, c_close)
    body_bot = min(c_open, c_close)
    wick_above = c_high - body_top
    wick_below = body_bot - c_low

    # Upside sweep
    if c_high > struct_high and c_close < struct_high and wick_above > 0.5 * candle_range:
        return LiquiditySweepResult(True, "upside", round(wick_above / atr, 4))

    # Downside sweep
    if c_low < struct_low and c_close > struct_low and wick_below > 0.5 * candle_range:
        return LiquiditySweepResult(True, "downside", round(wick_below / atr, 4))

    return LiquiditySweepResult()
