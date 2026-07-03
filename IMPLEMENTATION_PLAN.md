# Adaptive Quantitative Trading System — Full Implementation Plan

> **For AI Agents**: This document is a complete, step-by-step execution guide. Each phase is self-contained with file targets, formulas, pseudocode, data schemas, and acceptance criteria. Read the full phase before writing any code. Do not skip sections. Cross-references between phases are marked with `→ see Phase X`.

---

## Table of Contents

- [System Overview](#system-overview)
- [Repository Layout (Final State)](#repository-layout-final-state)
- [Phase A — Multi-Timeframe Architecture](#phase-a--multi-timeframe-architecture)
- [Phase B — Strategy Archetype System](#phase-b--strategy-archetype-system)
- [Phase C — Risk Engine Overhaul](#phase-c--risk-engine-overhaul)
- [Phase D — Feature Engineering Expansion](#phase-d--feature-engineering-expansion)
- [Phase E — Intelligence Layer Evolution](#phase-e--intelligence-layer-evolution)
- [Phase F — Validation Hardening](#phase-f--validation-hardening)
- [Phase G — Backtesting Professionalization](#phase-g--backtesting-professionalization)
- [Execution Priority Order](#execution-priority-order)
- [Cross-Phase Data Contracts](#cross-phase-data-contracts)
- [Testing & Acceptance Checklist](#testing--acceptance-checklist)

---

## System Overview

### What This System Is

An adaptive quantitative trading research platform for BTC/USDT (extensible to other pairs). The system:

- Ingests multi-timeframe OHLCV data
- Detects market regimes (trending, sideways, breakout, high-volatility)
- Selects the correct strategy archetype for each regime
- Sizes positions using volatility-aware risk controls
- Stores all decisions in MongoDB for replay and audit
- Runs an intelligence layer that evaluates strategy health and proposes config changes
- Validates those changes statistically before applying them

### What This System Is NOT

- Not a black-box neural execution engine
- Not an autonomous trading bot
- Not a reinforcement learning agent
- Not a black-box LLM decision maker

All trade execution remains **deterministic and rule-based**. The AI/intelligence layer only **evaluates, recommends, and flags**. A human (or a separate gated approval step) must accept recommendations before they modify live config.

### Existing Stack (Do Not Remove)

```
FastAPI            — signal API server
MongoDB            — persistence layer
Replay Engine      — historical trade simulation
Walk-Forward       — time-series cross-validation
Adaptive Config    — live parameter store
Validation Engine  — config approval gate
Trade Intelligence — memory of past trades
Regime Detection   — market state classifier
Analytics Dashboard— reporting UI
Strategy Recommender— existing (shallow) recommendation layer
```

The refactor **extends** these; it does not replace them wholesale. Each phase section calls out exactly which files to modify vs. create new.

---

## Repository Layout (Final State)

After all phases are complete the project tree should look like this. Use this as the north-star when creating files.

```
signal-engine/
│
├── main.py                          # FastAPI entrypoint (exists)
├── config.py                        # Central config loader (exists)
│
├── services/
│   ├── signal_engine.py             # MODIFIED — Phase A
│   ├── candle_loader.py             # MODIFIED — Phase A
│   ├── replay_engine.py             # MODIFIED — Phase A, G
│   ├── db.py                        # MODIFIED — Phase A, E
│   └── regime_engine.py             # MODIFIED — Phase A, B
│
├── strategies/                      # NEW — Phase B
│   ├── __init__.py
│   ├── base_strategy.py             # Abstract base class
│   ├── trend_following.py
│   ├── mean_reversion.py
│   ├── breakout.py
│   ├── volatility_expansion.py
│   └── strategy_manager.py
│
├── risk/                            # NEW — Phase C
│   ├── __init__.py
│   ├── atr_risk.py                  # ATR-based SL/TP
│   ├── position_sizer.py            # Dynamic sizing
│   └── global_risk_controls.py     # Circuit breakers
│
├── features/                        # NEW — Phase D
│   ├── __init__.py
│   ├── liquidity.py                 # Sweep / stop-hunt detection
│   ├── volatility.py                # Compression, expansion
│   ├── structure.py                 # S/R mapping
│   ├── trend_strength.py            # Persistence scoring
│   └── volume_analysis.py          # Imbalance, delta
│
├── intelligence/                    # NEW/EXPANDED — Phase E
│   ├── __init__.py
│   ├── strategy_evaluator.py        # Health scoring per strategy
│   ├── regime_evaluator.py          # Regime reliability
│   ├── trade_quality_evaluator.py  # Expectancy, frequency filters
│   ├── risk_escalation.py           # Drawdown / correlation alerts
│   └── recommendation_engine.py    # Produces actionable recommendations
│
├── validation/                      # EXPANDED — Phase F
│   ├── __init__.py
│   ├── statistical_guard.py         # Sample size, inertia, stability
│   ├── walk_forward.py              # Existing + freeze enforcement
│   └── approval_gate.py            # Human/auto approval logic
│
├── backtesting/                     # EXPANDED — Phase G
│   ├── __init__.py
│   ├── slippage_model.py
│   ├── fee_model.py
│   ├── monte_carlo.py
│   └── equity_curve.py
│
└── tests/
    ├── test_phase_a.py
    ├── test_phase_b.py
    ├── test_phase_c.py
    ├── test_phase_d.py
    ├── test_phase_e.py
    ├── test_phase_f.py
    └── test_phase_g.py
```

---

## Phase A — Multi-Timeframe Architecture

### Overview

**Goal**: Eliminate 1-minute noise as a primary decision driver. Introduce a three-tier timeframe hierarchy where each timeframe has a single, well-defined responsibility.

**Why this matters**: 1-minute candles are the most manipulated, noise-heavy data in crypto markets. Stop hunts, fake wicks, and micro-spikes cause the current engine to enter and exit trades based on noise rather than structure. The fix is not to discard 1m data entirely — it is to demote it to an optional precision layer.

---

### A.1 Timeframe Responsibility Matrix

| Timeframe | Role | Used For | NOT Used For |
|---|---|---|---|
| 15m | Macro Bias | Trend direction, regime filter, macro S/R | Entry timing, stop placement |
| 5m | Execution | Entry signals, pullback detection, breakout confirmation | Regime classification |
| 1m | Refinement | Precision entry within 5m signal window | Any standalone signal generation |

---

### A.2 Data Pipeline Design

#### Candle Loader (`services/candle_loader.py`)

**Current state**: Loads a single timeframe.

**Required changes**: Extend to load three timeframes simultaneously and return a unified `MarketSnapshot` object.

```python
# Target function signature
def load_market_snapshot(
    symbol: str,
    exchange_client,
    lookback_15m: int = 100,   # number of 15m candles to fetch
    lookback_5m:  int = 200,   # number of 5m candles to fetch
    lookback_1m:  int = 60,    # number of 1m candles to fetch
) -> MarketSnapshot:
    ...
```

**`MarketSnapshot` dataclass** (define in `config.py` or a new `models.py`):

```python
@dataclass
class MarketSnapshot:
    symbol:     str
    timestamp:  datetime
    candles_15m: pd.DataFrame   # columns: open, high, low, close, volume
    candles_5m:  pd.DataFrame
    candles_1m:  pd.DataFrame
    regime:      str            # filled later by regime_engine
    bias_15m:    str            # "bullish" | "bearish" | "neutral"
```

**Alignment requirement**: All three DataFrames must be timestamp-aligned. The most recent 15m candle close must be ≤ the most recent 5m candle close. Use pandas `resample` or exchange API directly for each timeframe. Never fabricate candles by resampling 1m into 5m in production — always fetch each timeframe independently from the exchange.

---

### A.3 Bias Detection Logic (15m Layer)

The 15m timeframe produces a single directional bias value: `bullish`, `bearish`, or `neutral`. This value gates all downstream execution.

**Algorithm**:

```
1. Compute EMA_20 and EMA_50 on 15m close prices.
2. Compute ADX(14) on 15m OHLCV.
3. Classify:
   IF close > EMA_20 > EMA_50 AND ADX > 20:
       bias = "bullish"
   ELIF close < EMA_20 < EMA_50 AND ADX > 20:
       bias = "bearish"
   ELSE:
       bias = "neutral"
4. Store bias in MarketSnapshot.bias_15m
```

**EMA formula** (implement from scratch or use pandas-ta):

```
EMA_t = price_t × k + EMA_(t-1) × (1 - k)
where k = 2 / (period + 1)
```

**ADX formula**:

```
+DM = max(high_t - high_(t-1), 0)  if  high_t - high_(t-1) > low_(t-1) - low_t  else 0
-DM = max(low_(t-1) - low_t, 0)    if  low_(t-1) - low_t > high_t - high_(t-1)  else 0
TR  = max(high - low, |high - prev_close|, |low - prev_close|)
ATR = Wilder smoothed average of TR over 14 periods
+DI = 100 × (smoothed +DM / ATR)
-DI = 100 × (smoothed -DM / ATR)
DX  = 100 × |+DI - -DI| / (+DI + -DI)
ADX = Wilder smoothed average of DX over 14 periods
```

---

### A.4 Execution Signal Logic (5m Layer)

The 5m layer generates trade signals **only when the 15m bias agrees**.

**Pullback Entry Detection**:

```
Bullish pullback entry conditions (ALL must be true):
  1. bias_15m == "bullish"
  2. 5m RSI(14) < 45  (pullback into oversold on sub-timeframe)
  3. 5m close > EMA_20 on 5m  (still above trend)
  4. 5m volume on last candle > 1.2 × 20-period average volume
  5. Regime is TRENDING or BREAKOUT  (→ see Phase B)

Bearish pullback entry conditions (mirror of above):
  1. bias_15m == "bearish"
  2. 5m RSI(14) > 55
  3. 5m close < EMA_20 on 5m
  4. volume confirmation same as above
  5. Regime is TRENDING or BREAKOUT
```

---

### A.5 Refinement Layer (1m)

The 1m layer is **optional**. It is only consulted when:
- A valid 5m signal exists
- The `use_1m_refinement` config flag is `True`

Its sole purpose is to find a slightly better entry price within the same candle window.

```
1m refinement logic:
  IF signal direction is LONG:
      Wait for 1m RSI < 35 OR 1m close touches 1m EMA_8 from above
      Then enter. Max wait = 3 × 1m candles. If no refinement in 3m, enter at market.
  IF signal direction is SHORT: mirror logic
```

Do **not** use 1m data for stop placement. Stops are always calculated from 5m ATR (→ see Phase C).

---

### A.6 Regime Engine Integration (`services/regime_engine.py`)

**Current state**: Classifies regime on a single timeframe.

**Required change**: Classify regime using **15m data exclusively**. The regime classification feeds into the strategy manager (→ Phase B).

```python
def detect_regime(candles_15m: pd.DataFrame) -> str:
    """
    Returns one of: "TRENDING", "SIDEWAYS", "BREAKOUT", "HIGH_VOLATILITY"
    """
    ...
```

**Classification logic**:

```
Compute on 15m candles:
  ADX_14         — trend strength
  ATR_14         — absolute volatility
  ATR_pct        = ATR_14 / close × 100   (normalised volatility %)
  BB_width       = (BB_upper - BB_lower) / BB_mid   (Bollinger Band width)
  vol_20_avg     = 20-period average volume
  vol_ratio      = current_volume / vol_20_avg

Classification rules (evaluate in order):
  1. IF ATR_pct > 3.0 AND vol_ratio > 2.0:
         regime = "HIGH_VOLATILITY"
  2. ELIF ADX_14 > 25 AND BB_width > 0.04:
         regime = "TRENDING"
  3. ELIF BB_width < 0.02 AND ADX_14 < 20:
         if vol_ratio > 1.8 (compression release imminent):
             regime = "BREAKOUT"
         else:
             regime = "SIDEWAYS"
  4. ELSE:
         regime = "SIDEWAYS"
```

**Bollinger Band formula**:

```
BB_mid   = SMA(close, 20)
BB_std   = rolling std dev of close over 20 periods
BB_upper = BB_mid + 2 × BB_std
BB_lower = BB_mid - 2 × BB_std
BB_width = (BB_upper - BB_lower) / BB_mid
```

---

### A.7 Database Schema Changes (`services/db.py`)

Add a new collection `market_snapshots` to store each evaluated snapshot:

```json
{
  "_id":        "ObjectId",
  "symbol":     "BTCUSDT",
  "timestamp":  "ISODate",
  "bias_15m":   "bullish | bearish | neutral",
  "regime":     "TRENDING | SIDEWAYS | BREAKOUT | HIGH_VOLATILITY",
  "adx_15m":    42.3,
  "atr_15m":    580.0,
  "bb_width_15m": 0.038,
  "rsi_5m":     43.1,
  "signal_generated": true,
  "signal_direction": "LONG | SHORT | NONE"
}
```

---

### A.8 Modified Signal Engine Flow (`services/signal_engine.py`)

Replace the existing single-timeframe main loop with:

```
LOOP every N seconds (configurable):
  1. snapshot = candle_loader.load_market_snapshot(symbol)
  2. snapshot.regime  = regime_engine.detect_regime(snapshot.candles_15m)
  3. snapshot.bias_15m = compute_15m_bias(snapshot.candles_15m)
  4. strategy = strategy_manager.select(snapshot.regime)   # Phase B
  5. signal = strategy.evaluate(snapshot)
  6. if signal.direction != "NONE":
       sized_signal = risk_engine.apply(signal, snapshot)   # Phase C
       db.save(sized_signal)
       emit_signal(sized_signal)
  7. db.save_snapshot(snapshot)
```

---

### A.9 Acceptance Criteria — Phase A

- [ ] `load_market_snapshot` returns all three DataFrames with no NaN in the last 50 rows of each
- [ ] `bias_15m` is never computed from 5m or 1m data
- [ ] `detect_regime` uses only 15m candles
- [ ] 1m data is not loaded at all when `use_1m_refinement = False`
- [ ] All three timeframes stored in `market_snapshots` MongoDB collection
- [ ] Unit test: feed known trending 15m candles → assert `bias_15m = "bullish"` and `regime = "TRENDING"`

---

## Phase B — Strategy Archetype System

### Overview

**Goal**: Replace a single universal strategy with four modular, regime-specific strategy archetypes. Each strategy activates only in its target regime. A `StrategyManager` class orchestrates selection, performance tracking, and deactivation.

**Why this matters**: Applying mean-reversion logic during a strong trend causes the engine to fight the tape. Applying trend-following logic during consolidation causes excessive whipsaws. The fix is regime-conditional strategy routing.

---

### B.1 Abstract Base Class (`strategies/base_strategy.py`)

Every strategy inherits from this. Agents must not bypass it.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Signal:
    direction:   str    # "LONG" | "SHORT" | "NONE"
    confidence:  float  # 0.0 – 1.0
    entry_price: float
    raw_sl:      float  # pre-risk-engine stop loss price
    raw_tp:      float  # pre-risk-engine take profit price
    strategy_id: str
    regime:      str
    timestamp:   datetime

class BaseStrategy(ABC):
    strategy_id: str
    target_regimes: list[str]
    is_active: bool = True

    @abstractmethod
    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """Core signal logic. Must return a Signal dataclass."""
        ...

    @abstractmethod
    def get_performance_summary(self) -> dict:
        """Returns win_rate, expectancy, avg_rr, trade_count."""
        ...

    def deactivate(self, reason: str):
        self.is_active = False
        log(f"{self.strategy_id} deactivated: {reason}")

    def activate(self):
        self.is_active = True
```

---

### B.2 Strategy 1 — Trend Following (`strategies/trend_following.py`)

**Activates during**: `TRENDING` regime only.

**Core concept**: Enter in the direction of the trend after a pullback. Never chase breakouts; wait for price to retrace to a support/resistance zone before entering.

#### Signal Logic

```
Setup conditions (all must be true for LONG):
  1. regime == "TRENDING"
  2. bias_15m == "bullish"
  3. 5m EMA_20 is sloping upward (EMA_20[0] > EMA_20[3])
  4. 5m RSI pulled back into 40–55 range (was overbought, cooling)
  5. 5m price bounced off EMA_20 on 5m (low touched EMA, close above)
  6. Volume on bounce candle > 1.15 × 20-period avg

Confidence score:
  base = 0.5
  + 0.1 if ADX_15m > 30
  + 0.1 if RSI now turning up from < 50
  + 0.1 if volume > 1.5× avg
  + 0.1 if 15m candle structure is clean (small wicks)
  = max 0.9

Raw SL: 5m EMA_20 - 0.5 × ATR_5m   (below the trend line)
Raw TP: entry + 2.0 × (entry - SL)  (2:1 risk/reward minimum)
```

#### Disqualifiers

```
Do NOT generate signal if:
  - 15m candle has a wick > 60% of candle range (manipulation)
  - Last 3 candles on 5m are all the same colour (exhaustion)
  - ATR_5m > 2.0 × 20-period ATR average (abnormal spike)
```

---

### B.3 Strategy 2 — Mean Reversion (`strategies/mean_reversion.py`)

**Activates during**: `SIDEWAYS` regime only.

**Core concept**: Buy oversold extremes, sell overbought extremes inside a defined range. The range is defined by Bollinger Bands. Only trade near the edges of the range, never in the middle.

#### Signal Logic

```
LONG setup (buy the dip at lower band):
  1. regime == "SIDEWAYS"
  2. 5m close <= BB_lower on 5m  (price at lower band)
  3. 5m RSI(14) < 32              (oversold)
  4. Bullish candle closes above BB_lower (rejection confirmed)
  5. Volume on rejection candle > 1.0 × avg (any confirmation)
  6. BB_width < 0.035             (we are in a defined range)

SHORT setup (sell the top at upper band): mirror logic
  RSI > 68, close >= BB_upper, bearish candle rejection

Confidence:
  base = 0.5
  + 0.15 if RSI < 25 (deeply oversold) / > 75 (deeply overbought)
  + 0.1  if prior candle wick clearly rejected the band
  + 0.1  if range has held for > 8 candles (established range)
  = max 0.85

Raw SL: BB_lower - 0.3 × ATR_5m  (for LONG; just outside the band)
Raw TP: BB_mid                    (mid-band is natural target in ranging market)
```

#### Disqualifiers

```
Do NOT generate signal if:
  - ADX_15m > 22 (market may be transitioning to trend)
  - Price has already touched the opposite band in last 5 candles
  - Volume is decreasing into the band touch (no interest = no bounce)
```

---

### B.4 Strategy 3 — Breakout (`strategies/breakout.py`)

**Activates during**: `BREAKOUT` regime only.

**Core concept**: Trade the expansion of energy after compression. Breakout trades require volume confirmation to avoid false breakouts and stop hunts.

#### Compression Detection

```
A valid compression setup is identified when:
  - BB_width on 5m has been below 0.020 for at least 6 consecutive candles
  - ATR_5m has been contracting (ATR[0] < ATR[5])
  - ADX_15m is below 20 (low trend = coiling)
  - Volume has been declining (avg of last 6 < avg of prior 14)
```

#### Breakout Confirmation Signal

```
LONG breakout:
  1. 5m close breaks above the compression high (highest high of last 10 candles)
  2. Volume on breakout candle > 2.0 × 20-period avg  ← CRITICAL
  3. ATR on breakout candle > 1.3 × ATR_20_avg (energy expansion confirmed)
  4. 15m candle is not forming a major resistance (check structure.py → Phase D)

SHORT breakout: mirror — breaks below compression low

Confidence:
  base = 0.5
  + 0.2 if volume > 3.0 × avg (very high conviction)
  + 0.15 if breakout candle body > 70% of candle range (clean move)
  + 0.1  if 15m bias aligns (breakout direction matches macro bias)
  - 0.2  if prior false breakout in last 20 candles (pattern unreliable)

Raw SL: bottom of compression range  (below compression low for LONG)
Raw TP: entry + 1.5 × compression height  (measured move target)

Compression height = compression_high - compression_low
```

#### Disqualifiers

```
Do NOT generate signal if:
  - A liquidity sweep was detected in the last 3 candles  (→ Phase D)
  - Volume confirmation is absent
  - The breakout is into a major HTF resistance
```

---

### B.5 Strategy 4 — Volatility Expansion (`strategies/volatility_expansion.py`)

**Activates during**: `HIGH_VOLATILITY` regime only.

**Core concept**: In high-volatility environments, momentum continuation is the primary edge. Entries must be taken in the direction of the current impulse. Position sizes are reduced to compensate for wider stops.

#### Signal Logic

```
LONG setup:
  1. regime == "HIGH_VOLATILITY"
  2. Last 3 candles on 5m are all bullish (momentum confirmation)
  3. 5m RSI > 55 (momentum, not mean-reversion)
  4. Volume expanding: each of last 3 candles' volume > previous candle's volume
  5. ATR expanding: ATR_current > 1.2 × ATR_10_period_avg
  6. 15m bias == "bullish"

SHORT setup: mirror

Confidence:
  base = 0.45  (inherently lower; high-vol strategies are riskier)
  + 0.15 if 4th candle also bullish (sustained momentum)
  + 0.1  if volume on latest candle > 3 × avg
  + 0.15 if 15m just broke a key level confirming direction
  = max 0.85

Raw SL: low of the last bullish candle - 0.5 × ATR_5m  (tight; momentum should not pause)
Raw TP: entry + 1.2 × ATR_5m  (conservative; high vol = wide swings = realistic TP)
```

#### Disqualifiers

```
Reduce position size by 50% automatically (→ Phase C handles this):
  - ATR_pct > 5.0% (extreme volatility; max 50% normal size)

Do NOT generate signal if:
  - Last candle has a wick > 80% of its own body (exhaustion)
  - RSI > 85 (parabolic; reversal risk high)
```

---

### B.6 Strategy Manager (`strategies/strategy_manager.py`)

The strategy manager is the central router. The signal engine calls `strategy_manager.select(regime)` and receives back the active strategy instance.

#### Responsibilities

```
1. ROUTING
   - Maintain a registry of {regime → strategy instance}
   - Return the correct strategy for each regime
   - Return a NullStrategy if regime is unclassified

2. PERFORMANCE TRACKING
   - After each completed trade, call update_performance(strategy_id, trade_result)
   - Store win_rate, avg_rr, total_trades, expectancy per strategy

3. DEACTIVATION LOGIC
   Deactivate a strategy if:
     - win_rate < 35% over last 20 trades
     - avg_rr < 0.8 (not making enough per winner)
     - consecutive_losses >= 5
   Re-activate after 24 hours or if regime conditions significantly change

4. PRIORITY MANAGEMENT
   Future: when two strategies could both be active (e.g. BREAKOUT during TRENDING)
   the manager selects based on: regime confidence score + strategy historical win rate

5. PERFORMANCE LOGGING
   Write to MongoDB collection: strategy_performance
```

#### Strategy Registry

```python
STRATEGY_REGISTRY = {
    "TRENDING":       TrendFollowingStrategy(),
    "SIDEWAYS":       MeanReversionStrategy(),
    "BREAKOUT":       BreakoutStrategy(),
    "HIGH_VOLATILITY": VolatilityExpansionStrategy(),
}
```

#### Performance Schema (MongoDB: `strategy_performance`)

```json
{
  "strategy_id":    "trend_following",
  "regime":         "TRENDING",
  "period_start":   "ISODate",
  "period_end":     "ISODate",
  "total_trades":   47,
  "win_rate":       0.574,
  "avg_rr":         1.82,
  "expectancy":     0.44,
  "consecutive_losses": 0,
  "is_active":      true,
  "deactivation_reason": null
}
```

**Expectancy formula**:

```
expectancy = (win_rate × avg_win_R) - ((1 - win_rate) × avg_loss_R)
where R = risk unit (1.0 = risked exactly the stop)
```

---

### B.7 Acceptance Criteria — Phase B

- [ ] Each strategy only produces signals in its target regime
- [ ] `StrategyManager.select("TRENDING")` returns `TrendFollowingStrategy` instance
- [ ] `StrategyManager.select("UNKNOWN")` returns a `NullStrategy` that always returns `Signal(direction="NONE")`
- [ ] Deactivation triggers correctly after 5 consecutive losses
- [ ] `strategy_performance` collection is populated after each trade closes
- [ ] Unit test: inject 20 losing trades → assert strategy deactivates

---

## Phase C — Risk Engine Overhaul

### Overview

**Goal**: Replace fixed SL/TP logic with a volatility-aware, regime-sensitive risk system. Every trade's stop loss, take profit, and position size must be dynamically computed based on current market conditions.

**Why this matters**: A fixed 1% stop loss is too tight during high-volatility periods (gets stopped out by noise) and too wide during consolidation (accepts unnecessary risk). Volatility-normalised stops respect market structure.

---

### C.1 ATR-Based Stop Loss (`risk/atr_risk.py`)

**Core formula**:

```
ATR_SL = entry_price ± (ATR_14_on_5m × SL_multiplier)

For LONG:  SL = entry_price - (ATR × multiplier)
For SHORT: SL = entry_price + (ATR × multiplier)
```

**SL multiplier by regime**:

| Regime | Multiplier | Rationale |
|---|---|---|
| TRENDING | 1.5 | Trend has strong momentum; give room |
| SIDEWAYS | 0.8 | Tight range; tight stops valid |
| BREAKOUT | 2.0 | Volatile expansion; wider stop needed |
| HIGH_VOLATILITY | 2.5 | Extreme swings; protect against noise |

**Take Profit formula**:

```
TP = entry + (entry - SL) × RR_ratio

RR_ratio by regime:
  TRENDING:       2.0   (classic 1:2)
  SIDEWAYS:       1.2   (conservative; range targets are close)
  BREAKOUT:       2.5   (measured move; high reward potential)
  HIGH_VOLATILITY: 1.2  (fast targets; don't overstay welcome)
```

**Implementation**:

```python
def compute_sl_tp(
    signal: Signal,
    atr_5m: float,
    regime: str,
) -> tuple[float, float]:
    multipliers = {
        "TRENDING": (1.5, 2.0),
        "SIDEWAYS": (0.8, 1.2),
        "BREAKOUT": (2.0, 2.5),
        "HIGH_VOLATILITY": (2.5, 1.2),
    }
    sl_mult, rr = multipliers[regime]
    if signal.direction == "LONG":
        sl = signal.entry_price - atr_5m * sl_mult
        tp = signal.entry_price + (signal.entry_price - sl) * rr
    else:  # SHORT
        sl = signal.entry_price + atr_5m * sl_mult
        tp = signal.entry_price - (sl - signal.entry_price) * rr
    return sl, tp
```

---

### C.2 Dynamic Position Sizing (`risk/position_sizer.py`)

**Core framework**: Risk a fixed percentage of portfolio equity per trade. Adjust that percentage based on volatility and confidence.

**Formula**:

```
base_risk_pct     = config.base_risk_per_trade    (default: 1.0%)
volatility_scalar = clamp(1.0 / atr_pct, 0.3, 1.5)
   where atr_pct = ATR_5m / price × 100
confidence_scalar = signal.confidence              (0.0 – 1.0)

adjusted_risk_pct = base_risk_pct × volatility_scalar × confidence_scalar

dollar_risk       = portfolio_equity × (adjusted_risk_pct / 100)
stop_distance     = |entry_price - sl|
position_size_usd = dollar_risk / stop_distance × entry_price
position_size_qty = position_size_usd / entry_price
```

**Worked example**:

```
portfolio_equity  = $10,000
base_risk_pct     = 1.0%   → dollar_risk = $100
entry_price       = $60,000
ATR_5m            = $900    → atr_pct = 1.5%   → volatility_scalar = 0.667
signal.confidence = 0.75
adjusted_risk_pct = 1.0% × 0.667 × 0.75 = 0.50%
dollar_risk       = $10,000 × 0.005 = $50
sl                = $60,000 - (900 × 1.5) = $58,650
stop_distance     = $60,000 - $58,650 = $1,350
position_size_qty = $50 / $1,350 = 0.037 BTC
```

**Regime-based exposure cap**:

```
Max position sizes by regime (% of portfolio):
  TRENDING:        5%  of portfolio value
  SIDEWAYS:        3%  of portfolio value
  BREAKOUT:        4%  of portfolio value
  HIGH_VOLATILITY: 2%  of portfolio value  ← hard cap
```

---

### C.3 Global Risk Controls (`risk/global_risk_controls.py`)

These are circuit breakers that can pause all new trade entry regardless of signals.

#### Daily Drawdown Limit

```
max_daily_drawdown_pct = config.max_daily_drawdown  (default: 3%)

At the start of each UTC day:
  day_start_equity = current_equity

Every trade result:
  current_drawdown = (day_start_equity - current_equity) / day_start_equity × 100
  if current_drawdown >= max_daily_drawdown_pct:
      trading_paused = True
      emit_alert("Daily drawdown limit hit. Trading paused.")
      resume at 00:00 UTC next day
```

#### Consecutive Loss Counter

```
max_consecutive_losses = config.max_consecutive_losses  (default: 4)

Track:
  consecutive_losses counter (resets to 0 on any win)
  if consecutive_losses >= max_consecutive_losses:
      emit_alert("Consecutive loss limit hit.")
      reduce position sizes by 50% for next 10 trades
      do NOT pause trading entirely (let the system recover slowly)
```

#### Regime-Based Exposure Reduction

```
if regime == "HIGH_VOLATILITY":
    apply 50% size reduction on top of dynamic sizing
if regime classification changed in last 2 periods:
    apply 25% size reduction (regime unstable; wait for confirmation)
```

#### Emergency Pause

```
Trigger if any of:
  - current_drawdown > 2 × max_daily_drawdown (runaway loss day)
  - 3 consecutive losses in < 30 minutes (system malfunction possible)
  - ATR_pct > 8.0% (exchange anomaly or flash crash)

Action:
  trading_paused = True
  log CRITICAL alert
  require manual resume (flag in database, not auto-cleared)
```

---

### C.4 Risk Engine Entry Point

The signal engine calls a single function after receiving a signal:

```python
def apply_risk(
    signal: Signal,
    snapshot: MarketSnapshot,
    portfolio: PortfolioState,
) -> Optional[SizedSignal]:
    """
    Returns None if global risk controls block the trade.
    Returns SizedSignal with SL, TP, and quantity if trade is allowed.
    """
    if global_risk_controls.is_paused():
        return None
    sl, tp = atr_risk.compute_sl_tp(signal, snapshot.atr_5m, snapshot.regime)
    qty    = position_sizer.compute_size(signal, sl, snapshot, portfolio)
    return SizedSignal(signal=signal, sl=sl, tp=tp, quantity=qty)
```

---

### C.5 Acceptance Criteria — Phase C

- [ ] SL distance varies with ATR; doubling ATR must double SL distance
- [ ] Position size decreases as signal confidence decreases
- [ ] HIGH_VOLATILITY regime triggers 50% position size reduction
- [ ] Daily drawdown limit pauses trading and resumes next UTC day
- [ ] `apply_risk` returns `None` when trading is paused
- [ ] Unit test: simulate 4 consecutive losses → assert position sizes halved on 5th

---

## Phase D — Feature Engineering Expansion

### Overview

**Goal**: Extend the feature set beyond retail indicators (RSI, SMA, ATR) into market-structure-aware features that give the strategy layer information about **what the market is actually doing**, not just what a lagging indicator says.

**Why this matters**: Institutional order flow leaves fingerprints. Liquidity sweeps, volume imbalances, compression, and support/resistance zones can be detected computationally. These features improve signal quality without adding machine learning complexity.

---

### D.1 Existing Features (Keep As-Is)

These are retained and still used by strategies:

- RSI(14) — momentum oscillator
- ATR(14) — volatility baseline
- SMA(20), EMA(20), EMA(50) — trend references
- Volume — raw volume per candle

No changes required to these calculations.

---

### D.2 Liquidity Sweep Detection (`features/liquidity.py`)

**Concept**: A liquidity sweep occurs when price briefly spikes beyond a key level (sweeping stop orders) and then immediately reverses. This is often engineered by large participants to fill large orders at favorable prices. Detecting sweeps prevents the engine from entering on what looks like a breakout but is actually a trap.

**Algorithm**:

```python
def detect_liquidity_sweep(candles: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Analyzes the most recent candle against recent structure.
    Returns: {
        "sweep_detected": bool,
        "sweep_direction": "upside" | "downside" | None,
        "sweep_magnitude_atr": float,  # how far beyond level in ATR units
    }
    """
```

**Detection logic**:

```
1. Identify the recent structure:
   structure_high = max(high) over last `lookback` candles (excluding current)
   structure_low  = min(low)  over last `lookback` candles (excluding current)
   ATR = 14-period ATR

2. On the CURRENT candle, check:
   UPSIDE SWEEP (fake breakout above):
     - candle.high > structure_high  (broke above)
     - candle.close < structure_high  (closed back below)
     - wick_above = candle.high - max(candle.open, candle.close)
     - wick_above > 0.5 × candle_range  (wick is majority of range)
     → sweep_detected = True, direction = "upside"

   DOWNSIDE SWEEP (fake breakdown below):
     - candle.low < structure_low
     - candle.close > structure_low
     - wick_below = min(candle.open, candle.close) - candle.low
     - wick_below > 0.5 × candle_range
     → sweep_detected = True, direction = "downside"

3. Magnitude:
   sweep_magnitude_atr = wick_above_or_below / ATR
```

**Usage in strategies**: Any strategy should suppress a LONG signal if an upside sweep was detected in the last 2 candles (likely a trap). Mirror for SHORT.

---

### D.3 Volatility Compression (`features/volatility.py`)

**Concept**: Before a major move, volatility compresses. Measuring this compression helps identify high-probability breakout setups before the breakout candle appears.

**Metrics to compute**:

```python
def compute_volatility_features(candles: pd.DataFrame) -> dict:
    return {
        "bb_width":          float,   # current BB width
        "bb_width_percentile": float, # where current BB width sits in its 100-period history (0–100)
        "atr_ratio":         float,   # ATR[0] / ATR[10]  — <1.0 means contracting
        "is_compressed":     bool,    # bb_width_percentile < 20 AND atr_ratio < 0.85
        "compression_bars":  int,     # how many consecutive bars BB_width has been in bottom 20th percentile
    }
```

**BB width percentile**:

```
bb_width_history = rolling BB_width over last 100 candles
bb_width_percentile = percentile rank of current BB_width within that history
```

**Compression bars counter**:

```
count = 0
for each candle from most recent going back:
  if bb_width_percentile < 20:
    count += 1
  else:
    break
compression_bars = count
```

---

### D.4 Trend Persistence (`features/trend_strength.py`)

**Concept**: Measures the quality and consistency of the current trend. A strong persistent trend has candles that consistently close in the direction of the trend. A weak trend has many mixed candles even if price is drifting higher/lower.

**Metrics**:

```python
def compute_trend_persistence(candles: pd.DataFrame, period: int = 14) -> dict:
    return {
        "directional_ratio":  float,   # % of last N candles that closed in trend direction
        "avg_candle_body_pct": float,  # avg body size as % of ATR (higher = conviction)
        "trend_acceleration": float,   # slope of EMA over last 5 vs last 14 periods
        "persistence_score":  float,   # composite 0–1 score
    }
```

**Directional ratio**:

```
For a bullish trend (bias_15m == "bullish"):
  bullish_candles = count of candles where close > open in last N
  directional_ratio = bullish_candles / N
```

**Avg candle body %**:

```
body_size = |close - open|
candle_range = high - low
body_pct = body_size / candle_range  (0 = all wick, 1 = all body)
avg_candle_body_pct = mean of body_pct over last N candles
```

**Persistence score formula**:

```
persistence_score = (directional_ratio × 0.5) + (avg_candle_body_pct × 0.3) + (clamp(trend_acceleration, 0, 1) × 0.2)
```

---

### D.5 Volume Imbalance / Delta (`features/volume_analysis.py`)

**Concept**: On each candle, volume can be attributed to buyers (up-close candles) or sellers (down-close candles). Sustained imbalance in one direction indicates accumulation or distribution.

**Metrics**:

```python
def compute_volume_features(candles: pd.DataFrame, period: int = 10) -> dict:
    return {
        "buy_volume_ratio":   float,  # buy vol / total vol over period (0–1)
        "volume_delta":       float,  # buy_vol - sell_vol
        "volume_trend":       str,    # "increasing" | "decreasing" | "flat"
        "relative_volume":    float,  # current vol / avg vol over 20 periods
        "volume_climax":      bool,   # current vol > 3 × avg (potential exhaustion)
    }
```

**Buy/Sell volume approximation** (without tick data):

```
For each candle:
  buy_vol  = volume × (close - low) / (high - low)     [Buying pressure proxy]
  sell_vol = volume × (high - close) / (high - low)    [Selling pressure proxy]

  Special case: if high == low (doji), split 50/50
```

**Volume trend**:

```
vol_slope = linear regression slope of volume over last 10 candles
if vol_slope > 0.05 × avg_volume:    "increasing"
elif vol_slope < -0.05 × avg_volume: "decreasing"
else:                                "flat"
```

---

### D.6 Support & Resistance Mapping (`features/structure.py`)

**Concept**: Identify price levels where the market has repeatedly reversed. These levels act as magnets and barriers. Entering a trade into a strong resistance level dramatically reduces probability of success.

**Algorithm**:

```python
def compute_structure_levels(
    candles_15m: pd.DataFrame,
    tolerance_atr: float = 0.5,
    min_touches: int = 2,
    lookback: int = 100,
) -> dict:
    return {
        "resistance_levels": list[float],  # sorted descending, nearest first
        "support_levels":    list[float],  # sorted ascending, nearest first
        "nearest_resistance": float,
        "nearest_support":    float,
        "distance_to_resistance_atr": float,
        "distance_to_support_atr":    float,
    }
```

**Level detection**:

```
1. On 15m candles (last `lookback` periods):
   Find all swing highs: candle where high > high of 2 candles before AND 2 candles after
   Find all swing lows:  candle where low < low of 2 candles before AND 2 candles after

2. Cluster nearby levels:
   Two swing points are the "same level" if |price_a - price_b| < ATR × tolerance_atr
   Merge clusters: take the mean price of all points in a cluster

3. Count touches:
   A level is valid only if it has >= min_touches

4. Sort and return nearest levels relative to current price
```

**Usage**:

```
If distance_to_resistance_atr < 1.0 and signal.direction == "LONG":
    suppress signal OR reduce TP to nearest_resistance
```

---

### D.7 Feature Pipeline Integration

All features are computed in a single function called after `load_market_snapshot`:

```python
def compute_all_features(snapshot: MarketSnapshot) -> FeatureSet:
    return FeatureSet(
        liquidity   = detect_liquidity_sweep(snapshot.candles_5m),
        volatility  = compute_volatility_features(snapshot.candles_5m),
        trend       = compute_trend_persistence(snapshot.candles_5m),
        volume      = compute_volume_features(snapshot.candles_5m),
        structure   = compute_structure_levels(snapshot.candles_15m),
    )
```

The `FeatureSet` is attached to the `MarketSnapshot` and passed to all strategies.

---

### D.8 Acceptance Criteria — Phase D

- [ ] Liquidity sweep correctly identifies a wick-dominant candle that pierces structure and closes back
- [ ] Compression detection activates when BB_width is in bottom 20th percentile
- [ ] Volume delta is always in range [-total_vol, +total_vol]
- [ ] S/R levels are only returned if they have >= 2 touches
- [ ] Unit test: inject 10 swing-high candles with the same level → assert level appears in `resistance_levels`

---

## Phase E — Intelligence Layer Evolution

### Overview

**Goal**: Transform the existing shallow AI layer (which only adjusts indicator weights) into a strategy evaluator that monitors system health, detects performance degradation, and produces actionable recommendations that are queued for human-gated approval.

**Critical constraint**: The intelligence layer **never directly modifies live config**. It writes recommendations to a database collection. The Validation Engine (Phase F) and an approval gate process those recommendations before any config changes are applied.

---

### E.1 Strategy Health Evaluator (`intelligence/strategy_evaluator.py`)

**Purpose**: Score each strategy's current health on a rolling basis. Detect edge decay before it causes significant drawdown.

**Health metrics computed per strategy** (using last N completed trades for that strategy):

```python
@dataclass
class StrategyHealth:
    strategy_id:        str
    evaluation_period:  str         # "last_20_trades" | "last_7_days"
    trade_count:        int
    win_rate:           float       # 0–1
    expectancy:         float       # R-units
    avg_rr:             float
    max_consecutive_losses: int
    drawdown_in_period: float       # peak-to-trough equity in this strategy's trades
    health_score:       float       # 0–100 composite
    health_status:      str         # "HEALTHY" | "DEGRADING" | "CRITICAL"
    recommendation:     Optional[str]
```

**Health score formula**:

```
health_score = 0 to 100

Components:
  win_rate_score       = clamp(win_rate / 0.55, 0, 1) × 30     (30 pts max; 55% = full score)
  expectancy_score     = clamp(expectancy / 0.5, 0, 1) × 30    (30 pts max; 0.5R = full score)
  consistency_score    = clamp(1 - (max_consec_loss / 7), 0, 1) × 20  (20 pts; 7 losses = 0)
  drawdown_score       = clamp(1 - (drawdown / 0.10), 0, 1) × 20  (20 pts; 10% DD = 0)

health_score = sum of all components

Thresholds:
  health_score >= 60: "HEALTHY"
  health_score >= 35: "DEGRADING"
  health_score < 35:  "CRITICAL"
```

**Recommendations generated by health status**:

```
DEGRADING:
  → "Reduce {strategy_id} position sizes by 25% for next 15 trades"
  → "Increase minimum confidence threshold to 0.7 for {strategy_id}"

CRITICAL:
  → "Deactivate {strategy_id} immediately"
  → "Review {strategy_id} regime classification accuracy"
```

---

### E.2 Regime Reliability Evaluator (`intelligence/regime_evaluator.py`)

**Purpose**: Detect when the regime classifier is producing unstable or inaccurate classifications. A noisy regime detector causes strategy selection failures, which corrupt performance data.

**Metrics**:

```python
@dataclass
class RegimeReliability:
    evaluation_window_hours: int    # e.g., 24
    total_regime_changes:    int    # how many times regime changed
    avg_regime_duration_bars: float # average bars per regime classification
    regime_flip_rate:        float  # regime changes per hour
    unstable_periods:        int    # periods of < 3 bar regime duration
    reliability_score:       float  # 0–1
    is_reliable:             bool
```

**Reliability scoring**:

```
A stable regime should last at least 5–10 candles before changing.

regime_flip_rate = total_regime_changes / evaluation_window_hours

reliability_score:
  if avg_regime_duration_bars >= 10:  base = 1.0
  elif avg_regime_duration_bars >= 5:  base = 0.7
  else:                                base = 0.3

  if regime_flip_rate > 3 per hour: base -= 0.3   (too noisy)
  if unstable_periods > 5:          base -= 0.2

  reliability_score = clamp(base, 0, 1)
  is_reliable = reliability_score >= 0.6
```

**Recommendation if unreliable**:

```
→ "Regime classifier producing unstable results. Increase ADX threshold from 20 to 25."
→ "Reduce strategy switching sensitivity. Require 3 consecutive same-regime bars before switching."
```

---

### E.3 Trade Quality Evaluator (`intelligence/trade_quality_evaluator.py`)

**Purpose**: Detect when the system is generating low-quality trades (poor setup, weak conviction, excessive frequency).

**Metrics**:

```python
@dataclass
class TradeQuality:
    avg_confidence:       float   # mean signal confidence of trades taken
    low_confidence_rate:  float   # % of trades with confidence < 0.55
    trade_frequency_per_day: float
    avg_hold_time_minutes: float
    avg_mfe:              float   # mean favorable excursion (how far price went our way)
    avg_mae:              float   # mean adverse excursion (how far price went against us)
    mfe_mae_ratio:        float   # MFE/MAE > 1.0 is healthy; < 1.0 means trades go wrong first
```

**MAE/MFE definitions**:

```
MFE (Maximum Favorable Excursion):
  For a LONG trade:
    MFE = max(high) during trade duration - entry_price

MAE (Maximum Adverse Excursion):
  For a LONG trade:
    MAE = entry_price - min(low) during trade duration

Both stored in R-units: MFE_R = MFE / (entry_price - sl)
```

**Recommendations**:

```
if low_confidence_rate > 0.3:
  → "Too many low-confidence trades entering. Raise minimum confidence threshold from 0.5 to 0.6."

if mfe_mae_ratio < 0.8:
  → "Trades going adverse before favorable. Review entry timing — possible early entries."

if trade_frequency_per_day > 10:
  → "Excessive trade frequency detected. Risk of overtrading. Add minimum time between trades: 2h."
```

---

### E.4 Risk Escalation Detection (`intelligence/risk_escalation.py`)

**Purpose**: Detect emerging risk patterns that precede catastrophic drawdowns. Act early.

**Detection patterns**:

```
1. VOLATILITY INSTABILITY
   Trigger: ATR_pct has increased > 50% in last 4 hours vs prior 4 hours
   Action:  → "Reduce all position sizes by 40% for 6 hours."

2. CORRELATED LOSSES
   Trigger: 3+ losses all in the same regime with the same strategy in < 2 hours
   Action:  → "Possible adverse regime condition. Pause {strategy_id} for 4 hours."

3. DRAWDOWN ACCELERATION
   Trigger: Daily drawdown exceeded 50% of limit in first 25% of trading day
   Action:  → "Drawdown accelerating. Reduce base_risk_pct to 0.5% for remainder of day."

4. SLIPPAGE ANOMALY (using replay logs)
   Trigger: Average realized slippage > 2 × expected slippage over last 10 trades
   Action:  → "Execution quality degraded. Check exchange connectivity or reduce trade frequency."
```

---

### E.5 Recommendation Engine (`intelligence/recommendation_engine.py`)

**Purpose**: Aggregate all evaluator outputs, deduplicate and prioritize recommendations, and write them to MongoDB for approval.

```python
def generate_recommendations(
    strategy_health: list[StrategyHealth],
    regime_reliability: RegimeReliability,
    trade_quality: TradeQuality,
    risk_events: list[RiskEvent],
) -> list[Recommendation]:
    ...
```

**Recommendation schema** (MongoDB: `strategy_recommendations`):

```json
{
  "_id":             "ObjectId",
  "created_at":      "ISODate",
  "source_evaluator": "strategy_evaluator | regime_evaluator | trade_quality | risk_escalation",
  "priority":        "CRITICAL | HIGH | MEDIUM | LOW",
  "title":           "Deactivate breakout strategy",
  "description":     "Breakout strategy health score: 28/100. Win rate: 31% over 22 trades.",
  "proposed_change": {
    "parameter":     "strategies.breakout.is_active",
    "current_value": true,
    "proposed_value": false
  },
  "evidence": {
    "win_rate":      0.31,
    "expectancy":    -0.12,
    "trade_count":   22
  },
  "status":          "PENDING | APPROVED | REJECTED | APPLIED",
  "approved_by":     null,
  "applied_at":      null
}
```

**Deduplication rule**:

```
If a recommendation with the same `parameter` and `proposed_value` already exists
in PENDING status and was created < 24 hours ago, do not create a duplicate.
Update the existing record's `evidence` and `created_at` instead.
```

---

### E.6 New MongoDB Collections

| Collection | Written By | Read By |
|---|---|---|
| `strategy_performance` | StrategyManager (Phase B) | StrategyEvaluator |
| `regime_performance` | RegimeEngine (Phase A) | RegimeEvaluator |
| `feature_importance` | FeaturePipeline (Phase D) | TradeQualityEvaluator |
| `risk_events` | GlobalRiskControls (Phase C) | RiskEscalationDetector |
| `strategy_recommendations` | RecommendationEngine | ApprovalGate (Phase F) |

---

### E.7 Intelligence Layer Execution Schedule

The intelligence layer does **not** run on every tick. It runs on a schedule:

```
StrategyHealthEvaluator:     Every 1 hour (or after every 5 new trades)
RegimeReliabilityEvaluator:  Every 4 hours
TradeQualityEvaluator:       Every 6 hours
RiskEscalationDetector:      Every 15 minutes (near-real-time)
RecommendationEngine:        Every 1 hour (aggregates all evaluator outputs)
```

---

### E.8 Acceptance Criteria — Phase E

- [ ] `StrategyHealth.health_score` is always in range 0–100
- [ ] CRITICAL health status creates a `CRITICAL` priority recommendation
- [ ] Recommendations are never duplicated within 24 hours
- [ ] Intelligence layer never calls any function that modifies live config directly
- [ ] All evaluator outputs stored in MongoDB with timestamps
- [ ] Unit test: inject 22 trades with 31% win rate for breakout strategy → assert CRITICAL health recommendation created

---

## Phase F — Validation Hardening

### Overview

**Goal**: Create a robust statistical gate that prevents the system from applying unstable, noisy, or overfitted configuration changes. Every recommendation from Phase E must pass through this gate before it can modify live config.

**Why this matters**: Adaptive systems can overfit to recent noise and make their performance worse. The most common failure mode is: system sees 5 bad trades, reduces position sizes, misses the recovery, then increases sizes again into the next drawdown. Statistical guardrails prevent this.

---

### F.1 Minimum Sample Size Enforcement (`validation/statistical_guard.py`)

**Rule**: No performance-based recommendation is acted upon unless it is based on a statistically meaningful sample.

```
minimum_trades_for_strategy_change = 30
minimum_trades_for_regime_change   = 20
minimum_trades_for_threshold_change = 15

Validation function:
  def has_sufficient_sample(trade_count: int, change_type: str) -> bool:
      minimums = {
          "strategy_activation":  30,
          "strategy_deactivation": 30,
          "regime_parameter":     20,
          "threshold":            15,
          "risk_reduction":        5,   # Risk reductions can act faster
      }
      return trade_count >= minimums[change_type]
```

**Exception**: Risk escalation events (drawdown, emergency pause) can act on fewer trades because the risk of inaction exceeds the risk of premature action.

---

### F.2 Parameter Inertia

**Rule**: No single parameter can change by more than a set percentage per week. This prevents the system from swinging between extremes.

```
inertia_rules = {
    "indicator_weight":      0.05,   # max 5% change per week
    "confidence_threshold":  0.05,   # max 5pp change per week
    "position_size_scalar":  0.10,   # max 10% change per week
    "sl_multiplier":         0.10,   # max 10% change per week
    "base_risk_pct":         0.20,   # max 20% change per week
}

def is_within_inertia(parameter: str, current_value: float, proposed_value: float) -> bool:
    max_change_pct = inertia_rules.get(parameter, 0.05)
    actual_change_pct = abs(proposed_value - current_value) / current_value
    return actual_change_pct <= max_change_pct
```

If a proposed change violates inertia, it is not rejected — it is **capped** to the inertia limit and re-queued.

---

### F.3 Walk-Forward Freeze Enforcement (`validation/walk_forward.py`)

**Rule**: During an active walk-forward evaluation period, no adaptive config changes are allowed. Evaluation must occur on a frozen config to be valid.

```
Walk-forward evaluation cycle:
  Training window:     last 60 days of trades
  Test window:         next 20 days (frozen config)
  Evaluation:          compare train vs test performance

During test window (20 days):
  all recommendations status = "FROZEN — walk-forward in progress"
  no PENDING recommendations can be APPROVED

After test window completes:
  evaluate_walk_forward_results()
    if test_sharpe < 0.5 × train_sharpe:   flag overfitting
    if test_win_rate < train_win_rate - 0.10:  flag parameter degradation
  resume normal recommendation processing
```

---

### F.4 Stability Requirements

**Rule**: A proposed change must demonstrate stable improvement, not a short-term noisy improvement.

```python
def is_improvement_stable(
    metric_history: list[float],    # daily metric values (e.g., daily win rate)
    proposed_direction: str,        # "increase" or "decrease"
    min_improvement_days: int = 5,
) -> bool:
    """
    Returns True only if the metric has been improving consistently
    for at least `min_improvement_days` consecutive days.
    """
    if len(metric_history) < min_improvement_days:
        return False
    recent = metric_history[-min_improvement_days:]
    if proposed_direction == "increase":
        return all(recent[i] <= recent[i+1] for i in range(len(recent)-1))
    else:
        return all(recent[i] >= recent[i+1] for i in range(len(recent)-1))
```

---

### F.5 Approval Gate (`validation/approval_gate.py`)

**Purpose**: Final decision point before any recommendation modifies live config.

**Auto-approval rules** (no human required):

```
Auto-approve if ALL of the following:
  1. has_sufficient_sample() == True
  2. is_within_inertia() == True
  3. is_improvement_stable() == True
  4. walk-forward not in frozen period
  5. priority is LOW or MEDIUM
```

**Manual approval required**:

```
Require human confirmation if ANY:
  - priority == CRITICAL
  - proposed_change affects strategy activation/deactivation
  - proposed_change affects base_risk_pct
  - proposed_change is the 3rd or more recommendation applied in 7 days
```

**Application**:

```python
def apply_approved_recommendation(rec: Recommendation, config: ConfigStore):
    """
    Called only after status = "APPROVED".
    Modifies live config via ConfigStore.set().
    Logs the change with full audit trail.
    Updates recommendation status to "APPLIED".
    """
    config.set(rec.proposed_change.parameter, rec.proposed_change.proposed_value)
    rec.applied_at = datetime.utcnow()
    rec.status = "APPLIED"
    db.update_recommendation(rec)
    log_audit(rec)   # immutable audit log entry
```

---

### F.6 Acceptance Criteria — Phase F

- [ ] Recommendation with `trade_count = 10` for `strategy_deactivation` is rejected (needs 30)
- [ ] Proposed change of 15% on `indicator_weight` is capped to 5% by inertia
- [ ] All recommendations frozen during walk-forward test window
- [ ] CRITICAL priority recommendations cannot auto-approve
- [ ] Applied recommendations create an immutable audit log entry
- [ ] Unit test: run walk-forward with frozen config → assert 0 recommendations are applied during freeze window

---

## Phase G — Backtesting Professionalization

### Overview

**Goal**: Make the replay engine simulate real execution conditions with institutional-grade accuracy. A backtest that ignores slippage, fees, and latency systematically overstates performance and leads to false confidence.

---

### G.1 Slippage Model (`backtesting/slippage_model.py`)

**Concept**: In live markets, the price you see and the price you get are different. Slippage is the difference. It increases with:
- Market volatility (ATR)
- Order size relative to market depth
- Time of day (low liquidity hours)

**Model**:

```python
def compute_slippage(
    direction:     str,      # "LONG" | "SHORT"
    entry_price:   float,
    position_size_usd: float,
    atr_5m:        float,
    regime:        str,
    candle_type:   str,      # "breakout" | "normal"
) -> float:
    """
    Returns the adjusted fill price (worse than requested).
    """
```

**Formula**:

```
base_slippage_bps = 2     (2 basis points = 0.02% — baseline for BTC/USDT)

Adjustments:
  volatility_adj  = (atr_5m / entry_price) × 100   (add atr% to slippage)
  size_adj        = clamp(position_size_usd / 100_000, 0, 1.0) × 3  (large orders = more slippage)

  if regime == "HIGH_VOLATILITY": multiplier = 3.0
  elif candle_type == "breakout":  multiplier = 2.0
  else:                            multiplier = 1.0

  total_slippage_bps = (base_slippage_bps + volatility_adj + size_adj) × multiplier
  slippage_price = entry_price × (total_slippage_bps / 10_000)

For LONG:  fill_price = entry_price + slippage_price   (you buy slightly higher)
For SHORT: fill_price = entry_price - slippage_price   (you sell slightly lower)
```

---

### G.2 Fee Model (`backtesting/fee_model.py`)

**BTC/USDT perpetual (Binance default)**:

```
Maker fee: 0.02%
Taker fee: 0.05%

In backtest, assume TAKER for all market entries and exits (conservative).
fee_rate = 0.0005   (0.05%)

entry_fee = position_size_usd × fee_rate
exit_fee  = position_size_usd × fee_rate   (approximate; size may change slightly at exit)
total_fees_per_trade = entry_fee + exit_fee

Total fee impact on P&L:
  trade_pnl_gross = (exit_price - entry_price) × qty   (for LONG)
  trade_pnl_net   = trade_pnl_gross - total_fees_per_trade
```

Apply fees to every replay trade. This typically reduces gross P&L by 15–25% on short-hold-time strategies. If net P&L is negative after fees, the strategy has no edge.

---

### G.3 Monte Carlo Stress Testing (`backtesting/monte_carlo.py`)

**Concept**: A single backtest result is a single sample path. Monte Carlo simulates thousands of alternative orderings of the same trades to understand the distribution of outcomes and identify worst-case paths.

**Implementation**:

```python
def run_monte_carlo(
    trade_results:  list[float],     # list of net P&L values per trade (in R-units)
    n_simulations:  int = 1000,
    starting_equity: float = 10_000,
) -> MonteCarloResult:
```

**Algorithm**:

```
For each simulation i in 1..n_simulations:
  1. Shuffle trade_results randomly (with replacement — bootstrap)
  2. Apply slippage noise: for each trade, add Normal(mean=0, std=0.0003) random noise
  3. Apply latency noise: randomly skip 2% of trades (execution failure simulation)
  4. Compute equity curve from the shuffled, noised sequence
  5. Record: final_equity, max_drawdown, sharpe_ratio, calmar_ratio

Return:
  MonteCarloResult {
    median_final_equity:      float
    p5_final_equity:          float   (5th percentile — worst 5% of outcomes)
    p95_final_equity:         float   (best 5% of outcomes)
    median_max_drawdown:      float
    p95_max_drawdown:         float   (95th percentile drawdown — worst case)
    ruin_probability:         float   # % of simulations where equity fell below 50% starting equity
    sharpe_distribution:      list    # for histogram plotting
  }
```

**Key metrics to examine**:

```
ruin_probability < 5%       → acceptable risk
p95_max_drawdown < 25%      → acceptable worst case
median_sharpe > 0.8         → acceptable risk-adjusted return
```

---

### G.4 Equity Curve Analytics (`backtesting/equity_curve.py`)

**Metrics to compute from any equity curve**:

```python
@dataclass
class EquityCurveMetrics:
    sharpe_ratio:        float    # (annualized return - risk_free) / annualized_std
    sortino_ratio:       float    # penalizes only downside volatility
    calmar_ratio:        float    # annualized_return / max_drawdown
    max_drawdown_pct:    float    # largest peak-to-trough decline
    max_drawdown_duration_days: int   # longest time spent below prior equity high
    recovery_factor:     float    # total_profit / max_drawdown
    profit_factor:       float    # gross_profit / gross_loss
    win_rate:            float
    avg_win_R:           float
    avg_loss_R:          float
    expectancy_R:        float
    total_trades:        int
    avg_trades_per_day:  float
    longest_win_streak:  int
    longest_loss_streak: int
```

**Sharpe Ratio formula**:

```
daily_returns = equity_curve.pct_change().dropna()
annualized_return = daily_returns.mean() × 252
annualized_std    = daily_returns.std() × sqrt(252)
risk_free_rate    = 0.045   (4.5% — use current approximate risk-free rate)
sharpe_ratio      = (annualized_return - risk_free_rate) / annualized_std
```

**Sortino Ratio**:

```
downside_returns    = daily_returns[daily_returns < 0]
downside_std        = downside_returns.std() × sqrt(252)
sortino_ratio       = (annualized_return - risk_free_rate) / downside_std
```

**Calmar Ratio**:

```
calmar_ratio = annualized_return / max_drawdown_pct
```

**Maximum Drawdown**:

```
equity_peak    = equity_curve.cummax()
drawdown       = (equity_curve - equity_peak) / equity_peak
max_drawdown   = drawdown.min()   (will be negative; abs for percentage display)
```

**Drawdown duration**:

```
For each date where equity < prior peak:
  mark as "in drawdown"
Find longest consecutive run of "in drawdown" days
```

---

### G.5 Replay Engine Integration (`services/replay_engine.py`)

The existing replay engine must be modified to call the new backtesting models on every simulated trade:

```
For each replay trade:
  1. fill_price = slippage_model.compute_slippage(...)
  2. Use fill_price (not signal price) for entry
  3. trade_pnl_net = gross_pnl - fee_model.compute_fees(...)
  4. Record fill_price, gross_pnl, net_pnl, slippage_cost, fee_cost
  5. After full replay: compute_equity_curve_metrics(all_trades)
  6. Optionally: run_monte_carlo(trade_pnl_results) if config.monte_carlo_enabled
```

---

### G.6 Acceptance Criteria — Phase G

- [ ] Every replay trade has a fill price that differs from signal price by the slippage model
- [ ] Every replay trade has entry and exit fees deducted from P&L
- [ ] Monte Carlo with 1000 simulations completes in < 30 seconds
- [ ] `ruin_probability` is correctly computed as % of simulations where equity < 50% starting
- [ ] Equity curve metrics are stored to MongoDB `backtest_results` collection
- [ ] Unit test: feed 50 trades with fixed 1:2 RR, 50% win rate → assert Sharpe > 0 and profit_factor > 1.0

---

## Execution Priority Order

Implement phases in this exact order. Each phase is a dependency for the next.

```
STEP 1 → Phase A (Multi-Timeframe Architecture)
          Reason: Everything else depends on clean multi-timeframe data and regime detection.

STEP 2 → Phase B (Strategy Archetype System)
          Reason: Strategies consume the regime and bias outputs from Phase A.

STEP 3 → Phase C (Risk Engine)
          Reason: Risk engine processes Strategy signals from Phase B.

STEP 4 → Phase D (Feature Engineering)
          Reason: Features enhance strategy signal quality. Strategies must exist first (Phase B).

STEP 5 → Phase E (Intelligence Layer)
          Reason: Evaluators analyze performance of strategies (Phase B) and risk events (Phase C).

STEP 6 → Phase F (Validation Hardening)
          Reason: Validation gates the Intelligence Layer recommendations (Phase E).

STEP 7 → Phase G (Backtesting Professionalization)
          Reason: Backtesting validates all the above in simulation before live deployment.
```

**Do not begin Phase N+1 until Phase N passes its acceptance criteria.**

---

## Cross-Phase Data Contracts

These are the shared data objects passed between phases. Any agent implementing a phase must use these contracts exactly to ensure interoperability.

### `MarketSnapshot` (Phase A → all phases)

```python
@dataclass
class MarketSnapshot:
    symbol:       str
    timestamp:    datetime
    candles_15m:  pd.DataFrame
    candles_5m:   pd.DataFrame
    candles_1m:   pd.DataFrame
    regime:       str            # set by Phase A
    bias_15m:     str            # set by Phase A
    atr_5m:       float          # set by Phase A
    features:     FeatureSet     # set by Phase D
```

### `Signal` (Phase B → Phase C)

```python
@dataclass
class Signal:
    direction:    str        # "LONG" | "SHORT" | "NONE"
    confidence:   float      # 0.0 – 1.0
    entry_price:  float
    raw_sl:       float
    raw_tp:       float
    strategy_id:  str
    regime:       str
    timestamp:    datetime
```

### `SizedSignal` (Phase C → execution / replay)

```python
@dataclass
class SizedSignal:
    signal:       Signal
    sl:           float      # ATR-adjusted stop loss
    tp:           float      # ATR-adjusted take profit
    quantity:     float      # computed by position sizer
    dollar_risk:  float
    regime:       str
```

### `TradeResult` (Phase B, C, G → Phase E)

```python
@dataclass
class TradeResult:
    trade_id:       str
    strategy_id:    str
    regime:         str
    direction:      str
    entry_price:    float
    exit_price:     float
    sl:             float
    tp:             float
    quantity:       float
    gross_pnl:      float
    net_pnl:        float      # after fees
    fee_cost:       float
    slippage_cost:  float
    hold_time_min:  float
    mfe:            float
    mae:            float
    result:         str        # "WIN" | "LOSS" | "BREAKEVEN"
    r_multiple:     float      # net_pnl / (entry - sl) / quantity
```

### `Recommendation` (Phase E → Phase F)

Defined in full in Phase E.5 above. Status flow:

```
PENDING → APPROVED → APPLIED
PENDING → REJECTED
PENDING → FROZEN (during walk-forward)
PENDING → CAPPED (inertia limit applied; re-queued with capped value)
```

---

## Testing & Acceptance Checklist

Before marking any phase complete, every item in its acceptance criteria must be checked. In addition, run the following integration tests after all phases are implemented:

### Integration Test 1 — Full Signal Pipeline

```
Input:  100 candles of known trending BTC data (15m, 5m, 1m)
Steps:
  1. load_market_snapshot()
  2. detect_regime()          → expect "TRENDING"
  3. compute_15m_bias()       → expect "bullish"
  4. compute_all_features()
  5. strategy_manager.select("TRENDING").evaluate()
  6. apply_risk()
Output expectations:
  - SizedSignal with direction "LONG"
  - SL is ATR × 1.5 below entry (TRENDING multiplier)
  - TP is 2× the risk distance
  - Position size reduces if confidence < 0.7
```

### Integration Test 2 — Risk Circuit Breaker

```
Input:  Simulate 4 consecutive LOSS trades
Steps:
  1. Process 4 losing TradeResult objects
  2. Call global_risk_controls.check()
Output:
  - After 4th loss: consecutive_loss warning, sizes halved
  - Daily drawdown computed correctly
  - If drawdown hits limit: trading_paused = True
```

### Integration Test 3 — Recommendation Pipeline

```
Input:  Inject 35 trades for breakout strategy with 30% win rate
Steps:
  1. intelligence layer runs evaluation
  2. StrategyHealth computed: should be CRITICAL
  3. Recommendation created: deactivate breakout
  4. Validation gate checks: sufficient sample (35 >= 30) ✓
  5. Walk-forward not frozen ✓
  6. Priority = CRITICAL → requires manual approval
Output:
  - Recommendation in MongoDB with status "PENDING"
  - Status does NOT auto-change to "APPLIED"
```

### Integration Test 4 — Full Backtest with Slippage

```
Input:  50 simulated trades, 50% win rate, 1:2 RR, HIGH_VOLATILITY regime
Steps:
  1. replay_engine runs all 50 trades
  2. slippage_model applied to each fill
  3. fee_model deducts from each trade
  4. equity_curve computed
  5. monte_carlo runs 1000 simulations
Output:
  - Net P&L lower than gross P&L
  - Sharpe ratio > 0 (system should still be profitable)
  - ruin_probability < 20% (acceptable for high-vol regime)
  - All metrics stored to backtest_results collection
```

---

*This document is the single source of truth for the refactor. Any ambiguity between this plan and existing code should default to this plan. Preserve the existing MongoDB connection, FastAPI routes, and replay engine interface — refactor them, do not rewrite from scratch unless a phase explicitly says otherwise.*
