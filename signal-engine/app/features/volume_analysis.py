"""
volume_analysis.py — Volume imbalance and delta features (Phase D.5).
"""
import numpy as np
import pandas as pd
from app.core.models import VolumeFeatures


def compute_volume_features(candles: pd.DataFrame, period: int = 10) -> VolumeFeatures:
    if candles.empty or len(candles) < period + 1:
        return VolumeFeatures()

    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    volume = candles["volume"].astype(float)

    recent = candles.iloc[-period:]
    r_high = recent["high"].astype(float)
    r_low = recent["low"].astype(float)
    r_close = recent["close"].astype(float)
    r_vol = recent["volume"].astype(float)

    # Buy/sell volume approximation
    hl_range = r_high - r_low
    hl_range = hl_range.replace(0, np.nan)
    buy_vol = r_vol * (r_close - r_low) / hl_range
    sell_vol = r_vol * (r_high - r_close) / hl_range
    buy_vol = buy_vol.fillna(r_vol * 0.5)
    sell_vol = sell_vol.fillna(r_vol * 0.5)

    total_buy = float(buy_vol.sum())
    total_sell = float(sell_vol.sum())
    total_vol = total_buy + total_sell
    buy_ratio = total_buy / total_vol if total_vol > 0 else 0.5
    vol_delta = total_buy - total_sell

    # Volume trend (linear regression slope)
    vol_20 = volume.iloc[-20:] if len(volume) >= 20 else volume
    avg_vol = float(vol_20.mean())
    if len(vol_20) >= 5 and avg_vol > 0:
        x = np.arange(len(vol_20))
        slope = float(np.polyfit(x, vol_20.values, 1)[0])
        if slope > 0.05 * avg_vol:
            vol_trend = "increasing"
        elif slope < -0.05 * avg_vol:
            vol_trend = "decreasing"
        else:
            vol_trend = "flat"
    else:
        vol_trend = "flat"

    # Relative volume
    vol_20_avg = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else volume.mean()
    rel_vol = float(volume.iloc[-1] / vol_20_avg) if vol_20_avg > 0 else 1.0

    # Volume climax
    climax = rel_vol > 3.0

    return VolumeFeatures(
        buy_volume_ratio=round(buy_ratio, 4),
        volume_delta=round(vol_delta, 2),
        volume_trend=vol_trend,
        relative_volume=round(rel_vol, 4),
        volume_climax=climax,
    )
