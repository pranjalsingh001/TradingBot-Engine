"""
candle_loader.py — Multi-timeframe data pipeline (Phase A).

Loads 15m, 5m, and optionally 1m candles from MongoDB and returns
a unified MarketSnapshot object. Supports resampling fallback for historical data.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from app.core.models import MarketSnapshot

logger = logging.getLogger(__name__)


def resample_historical_candles(df: pd.DataFrame, interval: str, limit: int) -> pd.DataFrame:
    """Helper to resample 1m candles into higher timeframes for Replay mode."""
    if df.empty:
        return df

    # Ensure timestamp is datetime for resampling
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp_dt", inplace=True)

    # Define rule
    rule = "5Min" if interval == "5m" else "15Min"

    # Resample
    resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    # Restore timestamp column (ISO format)
    resampled["timestamp"] = resampled.index.map(lambda x: x.isoformat())
    resampled.reset_index(drop=True, inplace=True)

    # Return only the requested limit
    return resampled.tail(limit)


async def _fetch_candles(
    symbol: str,
    interval: str,
    limit: int,
    max_timestamp: Optional[str] = None,
    historical: bool = False,
) -> pd.DataFrame:
    """
    Fetch OHLCV candles for a single timeframe from MongoDB.
    Returns DataFrame with columns: open, high, low, close, volume, timestamp.
    """
    from app.core.config import settings
    from app.core.db import get_db
    db = get_db()
    symbol_upper = symbol.upper()

    if historical:
        collection_name = f"historical_{interval}_{symbol_upper.lower()}"
        query = {}
    else:
        collection_name = settings.mongo_collection
        query = {"symbol": symbol_upper, "interval": interval}

    if max_timestamp:
        query["timestamp"] = {"$lte": max_timestamp}

    collection = db[collection_name]

    cursor = (
        collection
        .find(
            query,
            {"_id": 0, "open": 1, "high": 1, "low": 1, "close": 1, "price": 1,
             "volume": 1, "timestamp": 1}
        )
        .sort("timestamp", -1)
        .limit(limit)
    )

    docs = await cursor.to_list(length=limit)

    if not docs:
        if historical and interval in ["5m", "15m"]:
            logger.info(f"[CandleLoader] Historical {interval} data missing. Falling back to resampling from 1m.")
            # Fetch more 1m candles to ensure we have enough for the requested interval limit
            lookback_factor = 15 if interval == "15m" else 5
            df_1m = await _fetch_candles(symbol, "1m", limit * lookback_factor, max_timestamp, historical)
            if not df_1m.empty:
                return resample_historical_candles(df_1m, interval, limit)

        logger.warning("[CandleLoader] No data for %s %s", symbol_upper, interval)
        return pd.DataFrame()

    df = pd.DataFrame(docs)
    df.sort_values("timestamp", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Normalise column names — ensure 'close' exists
    if "close" not in df.columns and "price" in df.columns:
        df["close"] = pd.to_numeric(df["price"], errors="coerce")
    else:
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

    for col in ("open", "high", "low", "volume"):
        if col not in df.columns:
            if col == "volume":
                df[col] = 0.0
            else:
                df[col] = df["close"]
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Also keep 'price' column for backward compatibility
    df["price"] = df["close"]

    df.dropna(subset=["close"], inplace=True)

    return df


async def load_market_snapshot(
    symbol: str,
    lookback_15m: int = 100,
    lookback_5m: int = 200,
    lookback_1m: int = 60,
    use_1m_refinement: bool = False,
    max_timestamp: Optional[str] = None,
    historical: bool = False,
) -> MarketSnapshot:
    """
    Load a multi-timeframe MarketSnapshot.

    Fetches 15m, 5m, and optionally 1m candles independently.
    The resulting MarketSnapshot's regime and bias_15m fields are
    populated downstream by regime_engine and bias detection.

    Parameters
    ----------
    symbol            : str   e.g. "BTCUSDT"
    lookback_15m      : int   number of 15m candles to fetch
    lookback_5m       : int   number of 5m candles to fetch
    lookback_1m       : int   number of 1m candles to fetch
    use_1m_refinement : bool  if False, skip 1m data entirely
    max_timestamp     : str   optional upper bound for replay
    historical        : bool  if True, use historical collections
    """
    candles_15m = await _fetch_candles(
        symbol, "15m", lookback_15m, max_timestamp, historical
    )
    candles_5m = await _fetch_candles(
        symbol, "5m", lookback_5m, max_timestamp, historical
    )

    if use_1m_refinement:
        candles_1m = await _fetch_candles(
            symbol, "1m", lookback_1m, max_timestamp, historical
        )
    else:
        candles_1m = pd.DataFrame()

    # Compute ATR on 5m if we have enough data
    atr_5m = 0.0
    if len(candles_5m) >= 15:
        atr_5m = _compute_atr_ohlc(candles_5m, period=14)

    now = datetime.now(timezone.utc)

    return MarketSnapshot(
        symbol=symbol.upper(),
        timestamp=now,
        candles_15m=candles_15m,
        candles_5m=candles_5m,
        candles_1m=candles_1m,
        atr_5m=atr_5m,
    )


def _compute_atr_ohlc(df: pd.DataFrame, period: int = 14) -> float:
    """Compute ATR from OHLC data using proper True Range."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    # True Range
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )

    if len(tr) < period:
        return float(np.mean(tr)) if len(tr) > 0 else 0.0

    # Wilder smoothed ATR
    atr = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period

    return round(float(atr), 4)


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute ADX (Average Directional Index) from OHLC data.
    Returns the latest ADX value.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    if len(df) < period + 1:
        return 0.0

    # +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) & (plus_dm > 0), 0.0
    )
    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) & (minus_dm > 0), 0.0
    )

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing (equivalent to EWM with alpha=1/period)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    smooth_plus_dm = plus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # +DI and -DI
    plus_di = 100.0 * smooth_plus_dm / atr
    minus_di = 100.0 * smooth_minus_dm / atr

    # DX and ADX
    di_sum = plus_di + minus_di
    di_sum = di_sum.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    latest = adx.iloc[-1]
    return round(float(latest), 4) if not np.isnan(latest) else 0.0


def compute_15m_bias(candles_15m: pd.DataFrame) -> str:
    """
    Compute directional bias from 15m candles.

    Algorithm:
        1. EMA_20, EMA_50 on 15m close
        2. ADX(14) on 15m OHLCV
        3. Classify: bullish / bearish / neutral
    """
    if len(candles_15m) < 50:
        return "neutral"

    close = candles_15m["close"].astype(float)
    ema_20 = compute_ema(close, 20)
    ema_50 = compute_ema(close, 50)

    latest_close = close.iloc[-1]
    latest_ema_20 = ema_20.iloc[-1]
    latest_ema_50 = ema_50.iloc[-1]

    adx = compute_adx(candles_15m, period=14)

    if latest_close > latest_ema_20 > latest_ema_50 and adx > 20:
        return "bullish"
    elif latest_close < latest_ema_20 < latest_ema_50 and adx > 20:
        return "bearish"
    else:
        return "neutral"
