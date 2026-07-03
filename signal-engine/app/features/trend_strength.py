"""
trend_strength.py — Trend persistence scoring (Phase D.4).
"""
import numpy as np
import pandas as pd
from app.core.models import TrendPersistenceFeatures


def compute_trend_persistence(candles: pd.DataFrame, period: int = 14, bias: str = "bullish") -> TrendPersistenceFeatures:
    if candles.empty or len(candles) < period + 1:
        return TrendPersistenceFeatures()

    close = candles["close"].astype(float)
    opn = candles["open"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)

    recent = candles.iloc[-period:]

    # Directional ratio
    if bias == "bullish":
        dir_candles = (recent["close"] > recent["open"]).sum()
    else:
        dir_candles = (recent["close"] < recent["open"]).sum()
    dir_ratio = dir_candles / period

    # Avg candle body %
    body = (recent["close"] - recent["open"]).abs()
    candle_range = recent["high"] - recent["low"]
    candle_range = candle_range.replace(0, np.nan)
    body_pct = (body / candle_range).dropna()
    avg_body_pct = float(body_pct.mean()) if len(body_pct) > 0 else 0.0

    # Trend acceleration: EMA slope last 5 vs last 14
    ema = close.ewm(span=20, adjust=False).mean()
    if len(ema) >= 14:
        slope_5 = (ema.iloc[-1] - ema.iloc[-5]) / 5 if len(ema) >= 5 else 0
        slope_14 = (ema.iloc[-1] - ema.iloc[-14]) / 14
        accel = slope_5 / (abs(slope_14) + 1e-10) if slope_14 != 0 else 0
    else:
        accel = 0.0

    accel_clamped = max(0, min(1, accel))

    # Persistence score
    score = dir_ratio * 0.5 + avg_body_pct * 0.3 + accel_clamped * 0.2

    return TrendPersistenceFeatures(
        directional_ratio=round(dir_ratio, 4),
        avg_candle_body_pct=round(avg_body_pct, 4),
        trend_acceleration=round(accel, 4),
        persistence_score=round(score, 4),
    )
