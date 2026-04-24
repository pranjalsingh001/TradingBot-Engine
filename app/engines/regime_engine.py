"""
regime_engine.py - Detect market behavior BEFORE taking trades (Phase 4).
"""
import pandas as pd
import numpy as np

def detect_regime(df: pd.DataFrame) -> str:
    """
    Classify BTC into:
    - TRENDING
    - SIDEWAYS
    - HIGH_VOLATILITY
    - LOW_VOLATILITY
    - BREAKOUT
    """
    if df.empty or len(df) < 50:
        return "UNKNOWN"
        
    close = df['price'].values
    high = df.get('high', df['price']).values
    low = df.get('low', df['price']).values
    
    # Calculate SMA 50 and 20
    sma50 = pd.Series(close).rolling(window=50).mean().values[-1]
    sma20_series = pd.Series(close).rolling(window=20).mean()
    sma20 = sma20_series.values[-1]
    
    # Calculate ATR (14)
    tr = np.maximum.reduce([
        high[1:] - low[1:], 
        np.abs(high[1:] - close[:-1]), 
        np.abs(low[1:] - close[:-1])
    ])
    atr = pd.Series(tr).rolling(window=14).mean().values[-1] if len(tr) >= 14 else 0.0
    
    # Calculate Bollinger Bands width (Volatility)
    std20 = pd.Series(close).rolling(window=20).std().values[-1]
    bb_width = (4 * std20) / sma20 if sma20 > 0 else 0
    
    # Momentum slope (rate of change of SMA20 over last 5 periods)
    if len(sma20_series) >= 6:
        slope = (sma20_series.values[-1] - sma20_series.values[-6]) / 5
    else:
        slope = 0
        
    current_price = close[-1]
    
    # Thresholds
    is_trending = abs(slope) > (current_price * 0.0005) # 0.05% slope per candle
    is_high_vol = bb_width > 0.02 # 2% BB width
    is_low_vol = bb_width < 0.005 # 0.5% BB width
    
    distance_from_sma = abs(current_price - sma50) / sma50
    is_breakout = distance_from_sma > 0.015 and is_high_vol
    
    if is_breakout:
        return "BREAKOUT"
    elif is_trending:
        return "TRENDING"
    elif is_high_vol:
        return "HIGH_VOLATILITY"
    elif is_low_vol:
        return "LOW_VOLATILITY"
    else:
        return "SIDEWAYS"
