"""
breakout.py — Breakout Strategy (Phase B.4).

Activates during: BREAKOUT regime only.
Core concept: Trade the expansion after compression. Requires volume confirmation.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.strategies.base_strategy import BaseStrategy
from app.core.models import MarketSnapshot, Signal

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):

    def __init__(self):
        super().__init__(
            strategy_id="breakout",
            target_regimes=["BREAKOUT"],
        )

    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """Breakout from compression with volume confirmation."""
        if not self.is_active:
            return self._make_no_signal()

        if snapshot.regime != "BREAKOUT":
            return self._make_no_signal()

        candles = snapshot.candles_5m
        if candles.empty or len(candles) < 30:
            return self._make_no_signal()

        close = candles["close"].astype(float)
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        volume = candles["volume"].astype(float)

        latest_close = close.iloc[-1]

        # ── Compression detection ────────────────────────────────────────────
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_w = (4 * bb_std) / bb_mid

        # BB_width below 0.020 for at least 6 candles
        if len(bb_w) < 7:
            return self._make_no_signal()

        compressed_bars = 0
        for i in range(1, min(20, len(bb_w))):
            if bb_w.iloc[-i] < 0.020:
                compressed_bars += 1
            else:
                break

        if compressed_bars < 6:
            return self._make_no_signal()

        # ATR contracting
        atr_series = self._compute_atr_series(candles, 14)
        if len(atr_series) < 6:
            return self._make_no_signal()
        if atr_series[-1] >= atr_series[-6]:
            return self._make_no_signal()

        # Volume declining
        if len(volume) >= 20:
            vol_recent = volume.iloc[-6:].mean()
            vol_prior = volume.iloc[-20:-6].mean()
            if vol_prior > 0 and vol_recent >= vol_prior:
                return self._make_no_signal()

        # ── Compression range ────────────────────────────────────────────────
        lookback = 10
        compression_high = high.iloc[-lookback:].max()
        compression_low = low.iloc[-lookback:].min()
        compression_height = compression_high - compression_low

        # Volume and ATR averages
        vol_avg_20 = volume.rolling(20).mean().iloc[-1]
        latest_vol = volume.iloc[-1]
        vol_ratio = latest_vol / vol_avg_20 if vol_avg_20 > 0 else 0

        atr_20_avg = np.mean(atr_series[-20:]) if len(atr_series) >= 20 else np.mean(atr_series)
        latest_atr = atr_series[-1]

        # ── Disqualifiers ────────────────────────────────────────────────────
        # Liquidity sweep in last 3 candles
        if snapshot.features and snapshot.features.liquidity.sweep_detected:
            return self._make_no_signal()

        # Volume confirmation absent
        if vol_ratio < 2.0:
            return self._make_no_signal()

        # ── LONG breakout ────────────────────────────────────────────────────
        if (latest_close > compression_high * 1.001
                and vol_ratio >= 2.5
                and latest_atr > 1.3 * atr_20_avg):

            confidence = self._compute_confidence(
                vol_ratio, candles, snapshot, compression_high, compression_low
            )
            entry = latest_close
            sl = compression_low
            tp = entry + 1.5 * compression_height

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

        # ── SHORT breakout ───────────────────────────────────────────────────
        if (latest_close < compression_low * 0.999
                and vol_ratio >= 2.5
                and latest_atr > 1.3 * atr_20_avg):

            confidence = self._compute_confidence(
                vol_ratio, candles, snapshot, compression_high, compression_low
            )
            entry = latest_close
            sl = compression_high
            tp = entry - 1.5 * compression_height

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

    def _compute_confidence(self, vol_ratio, candles, snapshot, comp_high, comp_low) -> float:
        base = 0.5
        # Very high volume
        if vol_ratio > 3.0:
            base += 0.2
        # Clean breakout candle (body > 70% of range)
        last = candles.iloc[-1]
        body = abs(last["close"] - last["open"])
        full = last["high"] - last["low"]
        if full > 0 and body / full > 0.7:
            base += 0.15
        # 15m bias aligns
        direction = "LONG" if last["close"] > comp_high else "SHORT"
        if (direction == "LONG" and snapshot.bias_15m == "bullish") or \
           (direction == "SHORT" and snapshot.bias_15m == "bearish"):
            base += 0.1
        # Prior false breakout penalty (simplified)
        close = candles["close"].astype(float)
        if len(close) >= 20:
            # Check for price crossing compression levels and reversing
            crosses = 0
            for i in range(-20, -1):
                if close.iloc[i] > comp_high and close.iloc[i + 1] < comp_high:
                    crosses += 1
                if close.iloc[i] < comp_low and close.iloc[i + 1] > comp_low:
                    crosses += 1
            if crosses > 0:
                base -= 0.2
        return max(0.0, min(base, 0.95))

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
