"""
mean_reversion.py — Mean Reversion Strategy (Phase B.3).

Activates during: SIDEWAYS regime only.
Core concept: Buy oversold extremes at lower BB, sell overbought at upper BB.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.strategies.base_strategy import BaseStrategy
from app.core.models import MarketSnapshot, Signal

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):

    def __init__(self):
        super().__init__(
            strategy_id="mean_reversion",
            target_regimes=["SIDEWAYS"],
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """Mean reversion at Bollinger Band extremes."""
        if not self.is_active:
            return self._make_no_signal()

        if snapshot.regime != "SIDEWAYS":
            return self._make_no_signal()

        candles = snapshot.candles_5m
        if candles.empty or len(candles) < 30:
            return self._make_no_signal()

        close = candles["close"].astype(float)
        volume = candles["volume"].astype(float)

        latest_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        # Bollinger Bands on 5m
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_w = (bb_upper - bb_lower) / bb_mid

        latest_bb_upper = bb_upper.iloc[-1]
        latest_bb_lower = bb_lower.iloc[-1]
        latest_bb_mid = bb_mid.iloc[-1]
        latest_bb_width = bb_w.iloc[-1] if not np.isnan(bb_w.iloc[-1]) else 0

        # RSI(14)
        rsi = self._compute_rsi(close, 14)

        # Volume
        vol_avg = volume.rolling(20).mean().iloc[-1]
        latest_vol = volume.iloc[-1]
        vol_ratio = latest_vol / vol_avg if vol_avg > 0 else 0

        # ATR
        atr_5m = snapshot.atr_5m if snapshot.atr_5m > 0 else 0.0

        # ── Disqualifiers ────────────────────────────────────────────────────
        # ADX > 22 means transitioning to trend
        if not snapshot.candles_15m.empty and len(snapshot.candles_15m) >= 15:
            from app.data.candle_loader import compute_adx
            adx = compute_adx(snapshot.candles_15m, period=14)
            if adx > 22:
                return self._make_no_signal()

        # Price touched opposite band in last 5 candles
        if len(close) >= 6:
            recent_highs = candles["high"].iloc[-6:-1].astype(float)
            recent_lows = candles["low"].iloc[-6:-1].astype(float)
            recent_bb_upper = bb_upper.iloc[-6:-1]
            recent_bb_lower = bb_lower.iloc[-6:-1]

        # Volume decreasing into band touch = no interest
        if vol_ratio < 1.0:
            return self._make_no_signal()

        # ── LONG setup (buy at lower band) ───────────────────────────────────
        is_bullish_candle = latest_close > candles["open"].iloc[-1]
        if (latest_close <= latest_bb_lower * 1.002
                and rsi < 30
                and is_bullish_candle
                and latest_close > latest_bb_lower
                and latest_bb_width < 0.035):

            confidence = self._compute_confidence(rsi, latest_bb_width, candles)
            entry = latest_close
            sl = latest_bb_lower
            tp = latest_bb_mid

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

        # ── SHORT setup (sell at upper band) ─────────────────────────────────
        is_bearish_candle = latest_close < candles["open"].iloc[-1]
        if (latest_close >= latest_bb_upper * 0.998
                and rsi > 70
                and is_bearish_candle
                and latest_close < latest_bb_upper
                and latest_bb_width < 0.035):

            confidence = self._compute_confidence(100 - rsi, latest_bb_width, candles)
            entry = latest_close
            sl = latest_bb_upper
            tp = latest_bb_mid

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

    def _compute_confidence(self, rsi, bb_width, candles) -> float:
        base = 0.5
        # Deeply oversold/overbought
        if rsi < 25:
            base += 0.15
        # Range established for > 8 candles
        close = candles["close"].astype(float)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_w = (4 * bb_std) / bb_mid
        if len(bb_w) >= 9:
            if all(bb_w.iloc[-i] < 0.035 for i in range(1, min(9, len(bb_w)))):
                base += 0.1
        # Wick rejection
        last = candles.iloc[-1]
        body = abs(last["close"] - last["open"])
        full = last["high"] - last["low"]
        if full > 0 and body / full > 0.5:
            base += 0.1
        return min(base, 0.85)

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

    def get_performance_summary(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "total_trades": self._total_trades,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "consecutive_losses": self._consecutive_losses,
            "is_active": self.is_active,
        }
