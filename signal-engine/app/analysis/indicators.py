"""
indicators.py — Pure, stateless indicator computation.

Inputs  : a Pandas Series of closing prices (float64, oldest->newest)
Outputs : scalar float values

No side-effects. No DB calls. No business logic.
These functions are unit-testable in complete isolation.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """
    Compute RSI using Wilder's smoothed moving average (industry standard).

    Parameters
    ----------
    prices : pd.Series  Closing prices, oldest first, len >= period + 1
    period : int        Lookback window (default: 14)

    Returns
    -------
    float — latest RSI value in range [0, 100]

    Raises
    ------
    ValueError if series is too short
    """
    if len(prices) < period + 1:
        raise ValueError(
            f"RSI requires at least {period + 1} data points, got {len(prices)}"
        )

    prices = prices.astype(float).reset_index(drop=True)
    delta = prices.diff()

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder's initial average (simple average for first window)
    avg_gain = gain.iloc[1 : period + 1].mean()
    avg_loss = loss.iloc[1 : period + 1].mean()

    # Wilder's smoothing for remaining bars
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gain.iloc[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss.iloc[i]) / period

    if avg_loss == 0:
        return 100.0  # no losses -> maximum strength

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return round(float(rsi), 4)


def compute_sma(prices: pd.Series, period: int = 50) -> float:
    """
    Compute Simple Moving Average for the latest `period` bars.

    Parameters
    ----------
    prices : pd.Series  Closing prices, oldest first, len >= period
    period : int        Lookback window (default: 50)

    Returns
    -------
    float — latest SMA value

    Raises
    ------
    ValueError if series is too short
    """
    if len(prices) < period:
        raise ValueError(
            f"SMA-{period} requires at least {period} data points, got {len(prices)}"
        )

    sma = prices.iloc[-period:].mean()
    return round(float(sma), 4)


def compute_atr(prices: pd.Series, period: int = 14) -> float:
    """
    Compute Average True Range (simplified for close-only data).

    Uses absolute price differences as a proxy for true range.
    When OHLC data is available, replace with proper TR calculation.

    Parameters
    ----------
    prices : pd.Series  Closing prices, oldest first, len >= period + 1
    period : int        Lookback window (default: 14)

    Returns
    -------
    float — latest ATR value

    Raises
    ------
    ValueError if series is too short
    """
    if len(prices) < period + 1:
        raise ValueError(
            f"ATR requires at least {period + 1} data points, got {len(prices)}"
        )

    prices = prices.astype(float).reset_index(drop=True)
    # Simplified TR: absolute close-to-close difference
    true_range = prices.diff().abs()

    # Wilder's smoothed ATR
    atr = true_range.iloc[1 : period + 1].mean()
    for i in range(period + 1, len(prices)):
        atr = (atr * (period - 1) + true_range.iloc[i]) / period

    return round(float(atr), 4)
