"""
trend_following.py — Trend Following Strategy (Phase B.2).

Activates during: TRENDING regime only.
Core concept: Enter in the direction of the trend after a pullback.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.strategies.base_strategy import BaseStrategy
from app.core.models import MarketSnapshot, Signal

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(BaseStrategy):

    def __init__(self):
        super().__init__(
            strategy_id="trend_following",
            target_regimes=["TRENDING"],
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """Trend-following pullback entry logic on 5m data."""
        if not self.is_active:
            return self._make_no_signal()

        if snapshot.regime != "TRENDING":
            return self._make_no_signal()

        candles = snapshot.candles_5m
        if candles.empty or len(candles) < 30:
            return self._make_no_signal()

        close = candles["close"].astype(float)
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        volume = candles["volume"].astype(float)

        latest_close = close.iloc[-1]
        ema_20 = close.ewm(span=20, adjust=False).mean()
        latest_ema_20 = ema_20.iloc[-1]

        # RSI(14) on 5m
        rsi = self._compute_rsi(close, 14)

        # Volume check
        vol_avg_20 = volume.rolling(20).mean().iloc[-1]
        latest_vol = volume.iloc[-1]
        vol_ratio = latest_vol / vol_avg_20 if vol_avg_20 > 0 else 0

        # ATR on 5m
        atr_5m = snapshot.atr_5m if snapshot.atr_5m > 0 else self._compute_atr(candles)

        # EMA slope (upward or downward over last 3 bars)
        ema_slope_up = ema_20.iloc[-1] > ema_20.iloc[-4] if len(ema_20) > 4 else False
        ema_slope_down = ema_20.iloc[-1] < ema_20.iloc[-4] if len(ema_20) > 4 else False

        # ── Disqualifiers ────────────────────────────────────────────────────
        # 15m candle has wick > 60% of range (manipulation)
        if not snapshot.candles_15m.empty and len(snapshot.candles_15m) > 0:
            last_15m = snapshot.candles_15m.iloc[-1]
            candle_range = last_15m["high"] - last_15m["low"]
            if candle_range > 0:
                body_top = max(last_15m["open"], last_15m["close"])
                body_bot = min(last_15m["open"], last_15m["close"])
                wick = (last_15m["high"] - body_top) + (body_bot - last_15m["low"])
                if wick > 0.6 * candle_range:
                    return self._make_no_signal()

        # Last 3 candles all same colour (exhaustion)
        if len(close) >= 4:
            last3_bullish = all(candles["close"].iloc[-i] > candles["open"].iloc[-i] for i in range(1, 4))
            last3_bearish = all(candles["close"].iloc[-i] < candles["open"].iloc[-i] for i in range(1, 4))
            if last3_bullish or last3_bearish:
                return self._make_no_signal()

        # ATR spike check
        atr_values = self._compute_atr_series(candles, 14)
        if len(atr_values) > 20:
            atr_20_avg = np.mean(atr_values[-20:])
            if atr_values[-1] > 2.0 * atr_20_avg:
                return self._make_no_signal()

        # ── LONG Setup ───────────────────────────────────────────────────────
        if (snapshot.bias_15m == "bullish"
                and ema_slope_up
                and 40 <= rsi <= 60
                and latest_close > latest_ema_20
                and low.iloc[-1] <= latest_ema_20 * 1.003  # bounced off EMA
                and vol_ratio > 1.1):

            confidence = self._compute_confidence(snapshot, rsi, vol_ratio, candles)
            entry = latest_close
            sl = latest_ema_20
            tp = 0.0

            return Signal(
                direction="LONG",
                confidence=confidence,
                entry_price=round(entry, 2),
                raw_sl=round(sl, 2),
                raw_tp=round(tp, 2),
                strategy_id=self.strategy_id,
                regime=snapshot.regime,
                timestamp=datetime.utcnow(),
            )

        # ── SHORT Setup (mirror) ─────────────────────────────────────────────
        if (snapshot.bias_15m == "bearish"
                and ema_slope_down
                and 40 <= rsi <= 60
                and latest_close < latest_ema_20
                and high.iloc[-1] >= latest_ema_20 * 0.997
                and vol_ratio > 1.1):

            confidence = self._compute_confidence(snapshot, rsi, vol_ratio, candles)
            entry = latest_close
            sl = latest_ema_20
            tp = 0.0

            return Signal(
                direction="SHORT",
                confidence=confidence,
                entry_price=round(entry, 2),
                raw_sl=round(sl, 2),
                raw_tp=round(tp, 2),
                strategy_id=self.strategy_id,
                regime=snapshot.regime,
                timestamp=datetime.utcnow(),
            )

        return self._make_no_signal()

    def _compute_confidence(self, snapshot, rsi, vol_ratio, candles) -> float:
        """Compute confidence score for trend following signal."""
        from app.data.candle_loader import compute_adx
        base = 0.5
        # ADX > 30 bonus
        if not snapshot.candles_15m.empty and len(snapshot.candles_15m) >= 15:
            adx = compute_adx(snapshot.candles_15m, period=14)
            if adx > 30:
                base += 0.1

        # RSI turning up from < 50
        if rsi < 50:
            base += 0.1

        # Volume > 1.5x avg
        if vol_ratio > 1.5:
            base += 0.1

        # Clean 15m candle (small wicks)
        if not snapshot.candles_15m.empty:
            last_15m = snapshot.candles_15m.iloc[-1]
            body = abs(last_15m["close"] - last_15m["open"])
            full_range = last_15m["high"] - last_15m["low"]
            if full_range > 0 and body / full_range > 0.6:
                base += 0.1

        return min(base, 0.9)

    def _compute_rsi(self, close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.iloc[1:period + 1].mean()
        avg_loss = loss.iloc[1:period + 1].mean()
        for i in range(period + 1, len(close)):
            avg_gain = (avg_gain * (period - 1) + gain.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss.iloc[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df["high"].astype(float).values
        low = df["low"].astype(float).values
        close = df["close"].astype(float).values
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        if len(tr) < period:
            return float(np.mean(tr)) if len(tr) > 0 else 0.0
        atr = np.mean(tr[:period])
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period
        return float(atr)

    def _compute_atr_series(self, df: pd.DataFrame, period: int = 14) -> list:
        high = df["high"].astype(float).values
        low = df["low"].astype(float).values
        close = df["close"].astype(float).values
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        if len(tr) < period:
            return list(tr)
        result = []
        atr = np.mean(tr[:period])
        result.append(atr)
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period
            result.append(atr)
        return result

    def get_performance_summary(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "total_trades": self._total_trades,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "consecutive_losses": self._consecutive_losses,
            "is_active": self.is_active,
        }
