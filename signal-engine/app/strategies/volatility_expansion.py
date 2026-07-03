"""
volatility_expansion.py — Volatility Expansion Strategy (Phase B.5).
Activates during: HIGH_VOLATILITY regime only.
"""
import logging
from datetime import datetime
import numpy as np
import pandas as pd
from app.strategies.base_strategy import BaseStrategy
from app.core.models import MarketSnapshot, Signal

logger = logging.getLogger(__name__)

class VolatilityExpansionStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(strategy_id="volatility_expansion", target_regimes=["HIGH_VOLATILITY"])

    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        if not self.is_active or snapshot.regime != "HIGH_VOLATILITY":
            return self._make_no_signal()
        candles = snapshot.candles_5m
        if candles.empty or len(candles) < 20:
            return self._make_no_signal()
        close = candles["close"].astype(float)
        volume = candles["volume"].astype(float)
        rsi = self._rsi(close, 14)
        atr_5m = snapshot.atr_5m
        # Disqualifiers
        last = candles.iloc[-1]
        body = abs(last["close"] - last["open"])
        full = last["high"] - last["low"]
        if full > 0 and body < full * 0.2:
            return self._make_no_signal()
        if rsi > 85 or rsi < 15:
            return self._make_no_signal()
        if len(candles) < 4:
            return self._make_no_signal()
        l3_bull = all(candles["close"].iloc[-i] > candles["open"].iloc[-i] for i in range(1, 4))
        l3_bear = all(candles["close"].iloc[-i] < candles["open"].iloc[-i] for i in range(1, 4))
        vol_exp = len(volume) >= 4 and all(volume.iloc[-i] < volume.iloc[-i+1] for i in range(2, 4))
        atr_s = self._atr_s(candles, 14)
        atr_exp = len(atr_s) >= 10 and atr_s[-1] > 1.2 * np.mean(atr_s[-10:])
        if l3_bull and rsi > 55 and vol_exp and atr_exp and snapshot.bias_15m == "bullish":
            conf = self._conf(candles, volume, snapshot)
            e = close.iloc[-1]
            return Signal("LONG", conf, round(e,2), round(candles["low"].iloc[-1]-0.5*atr_5m,2), round(e+1.2*atr_5m,2), self.strategy_id, snapshot.regime, datetime.utcnow())
        if l3_bear and rsi < 45 and vol_exp and atr_exp and snapshot.bias_15m == "bearish":
            conf = self._conf(candles, volume, snapshot)
            e = close.iloc[-1]
            return Signal("SHORT", conf, round(e,2), round(candles["high"].iloc[-1]+0.5*atr_5m,2), round(e-1.2*atr_5m,2), self.strategy_id, snapshot.regime, datetime.utcnow())
        return self._make_no_signal()

    def _conf(self, candles, volume, snapshot) -> float:
        b = 0.45
        if len(candles) >= 5 and all(candles["close"].iloc[-i] > candles["open"].iloc[-i] for i in range(1,5)):
            b += 0.15
        va = volume.rolling(20).mean().iloc[-1]
        if va > 0 and volume.iloc[-1] > 3*va:
            b += 0.1
        if snapshot.bias_15m in ("bullish","bearish"):
            b += 0.15
        return min(b, 0.85)

    def _rsi(self, c, p):
        d = c.diff(); g = d.clip(lower=0); l = (-d).clip(lower=0)
        ag = g.iloc[1:p+1].mean(); al = l.iloc[1:p+1].mean()
        for i in range(p+1, len(c)):
            ag = (ag*(p-1)+g.iloc[i])/p; al = (al*(p-1)+l.iloc[i])/p
        return 100.0 if al == 0 else round(100-(100/(1+ag/al)),2)

    def _atr_s(self, df, p=14):
        h,l,c = df["high"].astype(float).values, df["low"].astype(float).values, df["close"].astype(float).values
        tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
        if len(tr)<p: return list(tr)
        r=[]; a=np.mean(tr[:p]); r.append(a)
        for i in range(p,len(tr)): a=(a*(p-1)+tr[i])/p; r.append(a)
        return r

    def get_performance_summary(self):
        return {"strategy_id":self.strategy_id,"total_trades":self._total_trades,"win_rate":self.win_rate,"expectancy":self.expectancy,"consecutive_losses":self._consecutive_losses,"is_active":self.is_active}
