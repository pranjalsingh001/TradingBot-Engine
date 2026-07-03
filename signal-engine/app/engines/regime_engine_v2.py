"""
regime_engine_v2.py — Multi-timeframe regime detection (Phase A).

Classifies market regime using 15m data exclusively.
Returns one of: TRENDING, SIDEWAYS, BREAKOUT, HIGH_VOLATILITY.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def detect_regime_15m(candles_15m: pd.DataFrame) -> str:
    """
    Classify market regime from 15m candles.

    Classification rules (evaluated in order):
      1. HIGH_VOLATILITY: ATR_pct > 3.0 AND vol_ratio > 2.0
      2. TRENDING: ADX > 25 AND BB_width > 0.04
      3. BREAKOUT: BB_width < 0.02 AND ADX < 20 AND vol_ratio > 1.8
      4. SIDEWAYS: BB_width < 0.02 AND ADX < 20
      5. Default: SIDEWAYS

    Parameters
    ----------
    candles_15m : pd.DataFrame with columns: open, high, low, close, volume

    Returns
    -------
    str — "TRENDING" | "SIDEWAYS" | "BREAKOUT" | "HIGH_VOLATILITY"
    """
    if candles_15m.empty or len(candles_15m) < 50:
        return "SIDEWAYS"

    close = candles_15m["close"].astype(float)
    high = candles_15m["high"].astype(float)
    low = candles_15m["low"].astype(float)
    volume = candles_15m["volume"].astype(float)

    latest_close = close.iloc[-1]

    # ── ADX(14) ──────────────────────────────────────────────────────────────
    adx = _compute_adx(candles_15m, period=14)

    # ── ATR(14) and ATR_pct ──────────────────────────────────────────────────
    atr = _compute_atr(high, low, close, period=14)
    atr_pct = (atr / latest_close * 100) if latest_close > 0 else 0.0

    # ── Bollinger Band width ─────────────────────────────────────────────────
    bb_mid = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    latest_bb_mid = bb_mid.iloc[-1]
    bb_width = ((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / latest_bb_mid
                if latest_bb_mid > 0 else 0.0)

    # ── Volume ratio ─────────────────────────────────────────────────────────
    vol_20_avg = volume.rolling(window=20).mean().iloc[-1]
    current_vol = volume.iloc[-1]
    vol_ratio = (current_vol / vol_20_avg) if vol_20_avg > 0 else 1.0

    # ── Classification (evaluate in order) ───────────────────────────────────
    if atr_pct > 3.0 and vol_ratio > 2.0:
        regime = "HIGH_VOLATILITY"
    elif adx > 25 and bb_width > 0.04:
        regime = "TRENDING"
    elif bb_width < 0.02 and adx < 20:
        if vol_ratio > 1.8:
            regime = "BREAKOUT"
        else:
            regime = "SIDEWAYS"
    else:
        regime = "SIDEWAYS"

    logger.debug(
        "[Regime] ADX=%.2f ATR_pct=%.2f BB_width=%.4f vol_ratio=%.2f → %s",
        adx, atr_pct, bb_width, vol_ratio, regime,
    )

    return regime


def get_regime_metadata(candles_15m: pd.DataFrame) -> dict:
    """Return raw regime metrics for storage in market_snapshots collection."""
    if candles_15m.empty or len(candles_15m) < 50:
        return {"adx_15m": 0, "atr_15m": 0, "bb_width_15m": 0}

    close = candles_15m["close"].astype(float)
    high = candles_15m["high"].astype(float)
    low = candles_15m["low"].astype(float)

    adx = _compute_adx(candles_15m, period=14)
    atr = _compute_atr(high, low, close, period=14)

    bb_mid = close.rolling(window=20).mean().iloc[-1]
    bb_std = close.rolling(window=20).std().iloc[-1]
    bb_width = ((bb_mid + 2 * bb_std) - (bb_mid - 2 * bb_std)) / bb_mid if bb_mid > 0 else 0

    return {
        "adx_15m": round(adx, 2),
        "atr_15m": round(atr, 2),
        "bb_width_15m": round(bb_width, 4),
    }


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Compute ATR from OHLC series."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 0.0


def _compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Compute ADX from OHLC DataFrame."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    if len(df) < period + 1:
        return 0.0

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    smooth_plus = plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    smooth_minus = minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    plus_di = 100.0 * smooth_plus / atr
    minus_di = 100.0 * smooth_minus / atr

    di_sum = plus_di + minus_di
    di_sum = di_sum.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    val = adx.iloc[-1]
    return round(float(val), 2) if not np.isnan(val) else 0.0
