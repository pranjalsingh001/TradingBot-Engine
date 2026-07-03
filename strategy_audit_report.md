# 🛡️ Trading Bot Strategy Audit Report
**Date:** May 9, 2026
**Current Version:** 2.1.0 (Institutional Adaptive)

---

## 1. Core Architecture
The bot is a deterministic technical signal engine with an asynchronous intelligence layer. It operates on a per-candle basis (default 1m).

### 1.1 Decision Pipeline
1.  **Data Ingestion:** Fetches the last 250 candles from MongoDB.
2.  **Indicator Suite:**
    *   **RSI (14):** Momentum oscillator.
    *   **SMA (50 & 200):** Trend detection.
    *   **ATR (14):** Volatility measurement.
3.  **Regime Detection:** Classifies market into `TRENDING`, `SIDEWAYS`, `BREAKOUT`, `HIGH_VOLATILITY`, or `LOW_VOLATILITY`.
4.  **Factor Scoring:** Normalizes all indicators into a range of `[-1.0, 1.0]`.
5.  **Weighted Sum:** Combines scores into a `final_score`.
6.  **Thresholding:** Compares `final_score` against a `dynamic_threshold`.

---

## 2. The Intelligence Layer (AI Logic)
The intelligence layer uses **Walk-Forward Optimization**.
*   **Logic:** It looks at the performance (Win Rate, Profit Factor) of the last batch of trades.
*   **Action:** If performance is below target, it generates **Recommendations** to shift weights.
*   **Validation:** A "Validation Engine" checks if the sample size is sufficient (>5 trades) and if the weight change is safe (max 5% shift per cycle).

### 2.1 Current Bottleneck: Weight Stagnation
The AI currently toggles between two primary "Safe" templates:
1.  **Template A (Balanced):** 40% Momentum, 30% Trend, 20% Strength, 10% Volatility.
2.  **Template B (Aggressive):** 60% Momentum, 10% Trend, 10% Strength, 20% Volatility.

**Problem:** It fails to explore unique weight combinations (e.g., 0% Trend, 100% Momentum) because the "Overfitting Guard" prevents any factor from having >80% weight.

---

## 3. Mathematical Indicators & Scoring
### 3.1 Momentum (RSI)
*   **Formula:** `(50 - RSI) / 50`
*   **Intent:** Mean reversion. RSI < 50 = Bullish, RSI > 50 = Bearish.

### 3.2 Trend (SMA Divergence)
*   **Formula:** `((Price - SMA50) / SMA50) * 50.0`
*   **Intent:** Trend following. Price above SMA50 is Bullish.
*   **Recent Update:** Multiplied by 50.0 to increase sensitivity (otherwise scores were too tiny).

### 3.3 Disagreement Penalty
*   **Logic:** If Momentum is "Buy" but Trend is "Sell", the **Confidence is halved (50% penalty)**.
*   **Impact:** This is likely why confidence stays between 10-25%—the indicators are constantly fighting each other.

---

## 4. Performance Diagnosis (Why the 33% Win Rate?)
After analyzing 2000+ trades, we see the following:
1.  **Stop Loss / Take Profit Ratio:** Default is 1:2, but volatility often hits SL before TP.
2.  **Market Noise:** On the 1m timeframe, "Trend" signals are often fake-outs.
3.  **Low Alpha:** The combination of RSI and SMA is too generic for 2024 crypto markets.
4.  **Threshold Friction:** The `dynamic_threshold` (0.08 - 0.20) is often higher than the `final_score`, causing the bot to miss the beginning of big moves and enter too late.

---

## 5. Improvement Hypotheses for Next AI
1.  **Indicator Replacement:** Swap RSI for **MACD** or **Stochastic** for better entry timing.
2.  **Multi-Timeframe Analysis:** Only trade 1m if the 15m trend is in the same direction (Reduce Disagreement).
3.  **Volatility-Based SL/TP:** Instead of fixed points, use ATR-based exits.
4.  **Deepen Search Space:** Allow the AI to test weights between 0% and 100% without the 80% cap for short periods.

---
**Status:** Audit Complete. Ready for Strategic Overhaul.
