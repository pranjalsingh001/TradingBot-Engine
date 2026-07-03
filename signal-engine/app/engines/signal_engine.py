"""
signal_engine.py — Context-aware adaptive scoring engine.

Pipeline:
    1. Validate data
    2. Compute raw indicators (RSI, SMA50, SMA200, ATR)
    3. Detect market regime (TRENDING vs SIDEWAYS)
    4. Select dynamic weights based on regime
    5. Normalise indicators into factor scores [-1, 1]
    6. Weighted sum -> final_score
    7. Compute dynamic threshold based on volatility
    8. Apply disagreement penalty to confidence
    9. Signal decision: BUY / SELL / HOLD

Single responsibility: decision logic only.
No DB calls. No HTTP. No randomness.
"""

import json
import logging
import math
from typing import List, Dict, Tuple

import pandas as pd

from app.core.config import settings
from app.analysis.indicators import compute_rsi, compute_sma, compute_atr
from app.engines.regime_engine import detect_regime
from app.core.adaptive_config import apply_adaptive_weights
from app.core.schemas import (
    SignalResponse, IndicatorValues, FactorBreakdown,
    WeightBreakdown, ErrorResponse,
)

logger = logging.getLogger(__name__)

# ── Signal constants ──────────────────────────────────────────────────────────
BUY  = "BUY"
SELL = "SELL"
HOLD = "HOLD"

# ── Regime constants ──────────────────────────────────────────────────────────
REGIME_TRENDING  = "TRENDING"
REGIME_SIDEWAYS  = "SIDEWAYS"
REGIME_THRESHOLD = 0.02  # abs(price - MA50) / MA50 threshold

# ── Regime-dependent weights (must each sum to 1.0) ──────────────────────────
WEIGHTS_TRENDING = {
    "momentum":       0.2,
    "trend":          0.4,
    "trend_strength": 0.3,
    "volatility":     0.1,
}

WEIGHTS_SIDEWAYS = {
    "momentum":       0.5,
    "trend":          0.2,
    "trend_strength": 0.1,
    "volatility":     0.2,
}

WEIGHTS_BREAKOUT = {
    "momentum":       0.6,
    "trend":          0.1,
    "trend_strength": 0.1,
    "volatility":     0.2,
}

WEIGHTS_HIGH_VOLATILITY = {
    "momentum":       0.1,
    "trend":          0.2,
    "trend_strength": 0.2,
    "volatility":     0.5,
}

WEIGHTS_LOW_VOLATILITY = {
    "momentum":       0.4,
    "trend":          0.3,
    "trend_strength": 0.2,
    "volatility":     0.1,
}

# ── Threshold constants ──────────────────────────────────────────────────────
BASE_THRESHOLD       = 0.08  # Reduced slightly to allow more trades for intelligence to learn
VOLATILITY_PENALTY   = 0.15  # Reduced penalty for high vol to allow breakout trades
VOLATILITY_SCALE     = 50.0  # ATR/price scaling factor

# ── Disagreement penalty ─────────────────────────────────────────────────────
DISAGREEMENT_PENALTY = 0.5


# ── Regime detection ─────────────────────────────────────────────────────────

def compute_regime(df: pd.DataFrame, price: float, ma50: float) -> Tuple[str, float]:
    """
    Detect market regime based on price divergence from MA50 and regime_engine logic.

    Returns (regime, trend_strength_metric)
    """
    regime = detect_regime(df)
    
    if ma50 == 0:
        return regime, 0.0

    trend_strength_metric = abs(price - ma50) / ma50

    return regime, round(trend_strength_metric, 6)


def get_weights(regime: str) -> Dict[str, float]:
    """Return factor weights for the detected regime."""
    if regime == "BREAKOUT":
        base_weights = WEIGHTS_BREAKOUT
    elif regime == "HIGH_VOLATILITY":
        base_weights = WEIGHTS_HIGH_VOLATILITY
    elif regime == "LOW_VOLATILITY":
        base_weights = WEIGHTS_LOW_VOLATILITY
    elif regime == "TRENDING":
        base_weights = WEIGHTS_TRENDING
    else:
        base_weights = WEIGHTS_SIDEWAYS
        
    return apply_adaptive_weights(regime, base_weights)


# ── Factor computation (pure functions) ───────────────────────────────────────

def compute_momentum_score(rsi: float) -> float:
    """
    RSI-based momentum factor.

    rsi_score = (50 - rsi) / 50, clamped to [-1, 1]

    RSI < 50  -> positive (oversold, bullish)
    RSI > 50  -> negative (overbought, bearish)
    RSI = 50  -> neutral (0)
    """
    raw = (50.0 - rsi) / 50.0
    return max(-1.0, min(1.0, round(raw, 4)))


def compute_trend_score(price: float, ma50: float) -> float:
    """
    Price vs MA50 trend factor.

    trend_score = (price - MA50) / MA50, clamped to [-1, 1]
    """
    if ma50 == 0:
        return 0.0
    # Sensitize trend score: 1% move = 0.5 score
    raw = ((price - ma50) / ma50) * 50.0
    return max(-1.0, min(1.0, round(raw, 4)))


def compute_trend_strength_score(ma50: float, ma200: float) -> float:
    """
    MA50 vs MA200 trend strength.

    MA50 > MA200 -> +1 (uptrend)
    MA50 < MA200 -> -1 (downtrend)
    MA50 == MA200 -> 0 (indeterminate)
    """
    if ma50 > ma200:
        return 1.0
    elif ma50 < ma200:
        return -1.0
    return 0.0


def compute_volatility_score(atr: float, price: float) -> float:
    """
    ATR-normalised volatility factor.

    Low volatility  -> +1 (stable, higher confidence)
    High volatility -> -1 (risky, lower confidence)

    Steps:
        1. atr_ratio = ATR / price
        2. raw = 1 - min(atr_ratio * 50, 1)  -> [0, 1]
        3. score = (raw * 2) - 1              -> [-1, 1]
    """
    if price == 0:
        return 0.0
    atr_ratio = atr / price
    raw = 1.0 - min(atr_ratio * VOLATILITY_SCALE, 1.0)
    score = (raw * 2.0) - 1.0
    return max(-1.0, min(1.0, round(score, 4)))


# ── Dynamic threshold ────────────────────────────────────────────────────────

def compute_dynamic_threshold(atr: float, price: float) -> float:
    """
    Adjust signal threshold based on market volatility.

    Higher volatility -> higher threshold -> harder to trigger signals.

    dynamic_threshold = base + (volatility_level * penalty)
    """
    if price == 0:
        return BASE_THRESHOLD
    atr_ratio = atr / price
    volatility_level = min(atr_ratio * VOLATILITY_SCALE, 1.0)
    threshold = BASE_THRESHOLD + (volatility_level * VOLATILITY_PENALTY)
    return round(threshold, 4)


# ── Disagreement penalty ─────────────────────────────────────────────────────

def compute_disagreement(
    momentum: float, trend: float, trend_strength: float
) -> bool:
    """
    Detect whether factors disagree on direction.

    Returns True if both positive and negative signs exist
    among the three directional factors.
    """
    signs = []
    for val in (momentum, trend, trend_strength):
        if val > 0:
            signs.append(1)
        elif val < 0:
            signs.append(-1)
        # val == 0 is neutral, skip

    if not signs:
        return False

    has_positive = any(s > 0 for s in signs)
    has_negative = any(s < 0 for s in signs)
    return has_positive and has_negative


# ── Core engine ───────────────────────────────────────────────────────────────

def generate_signal(
    df: pd.DataFrame, symbol: str, interval: str
) -> SignalResponse | ErrorResponse:
    """
    Context-aware adaptive signal generation.

    Pipeline:
        1. Validate & deduplicate data
        2. Compute raw indicators
        3. Detect regime -> select weights
        4. Compute factor scores
        5. Weighted sum -> final_score
        6. Dynamic threshold from volatility
        7. Disagreement penalty on confidence
        8. Signal decision

    Parameters
    ----------
    df       : pd.DataFrame  price records, ASC sorted
    symbol   : str
    interval : str

    Returns
    -------
    SignalResponse on success, ErrorResponse on data error
    """
    symbol = symbol.upper()

    # ── Guard: Data Validation ────────────────────────────────────────────────
    if not df.empty and "timestamp" in df.columns:
        df = df.drop_duplicates(subset=["timestamp"])

    min_required = max(settings.rsi_period + 1, settings.ma_long_period)
    if df.empty or len(df) < min_required:
        msg = (
            f"Insufficient data: need {min_required} records, "
            f"got {len(df) if not df.empty else 0}"
        )
        logger.warning("[Engine] %s (%s) -> %s", symbol, interval, msg)
        return ErrorResponse(
            symbol=symbol, interval=interval, error=msg,
            signal=HOLD, score=0.0, confidence=0.0,
        )

    prices = df["price"]
    latest_price = round(float(prices.iloc[-1]), 4)

    # ── Step 1: Compute raw indicators ────────────────────────────────────────
    try:
        rsi   = compute_rsi(prices, period=settings.rsi_period)
        ma50  = compute_sma(prices, period=settings.ma_period)
        ma200 = compute_sma(prices, period=settings.ma_long_period)
        atr   = compute_atr(prices, period=settings.rsi_period)
    except ValueError as exc:
        logger.error("[Engine] Indicator error for %s: %s", symbol, exc)
        return ErrorResponse(
            symbol=symbol, interval=interval, error=str(exc),
            signal=HOLD, score=0.0, confidence=0.0,
        )

    indicators = IndicatorValues(
        rsi=rsi, ma=ma50, ma200=ma200, atr=atr, price=latest_price,
    )

    # ── Step 2: Detect regime ─────────────────────────────────────────────────
    regime, regime_metric = compute_regime(df, latest_price, ma50)

    # ── Step 3: Select weights ────────────────────────────────────────────────
    active_weights = get_weights(regime)

    weights_model = WeightBreakdown(
        momentum=active_weights["momentum"],
        trend=active_weights["trend"],
        trend_strength=active_weights["trend_strength"],
        volatility=active_weights["volatility"],
    )

    # ── Step 4: Compute factor scores ─────────────────────────────────────────
    momentum       = compute_momentum_score(rsi)
    trend          = compute_trend_score(latest_price, ma50)
    trend_strength = compute_trend_strength_score(ma50, ma200)
    volatility     = compute_volatility_score(atr, latest_price)

    factors = FactorBreakdown(
        momentum=momentum,
        trend=trend,
        trend_strength=trend_strength,
        volatility=volatility,
    )

    # ── Step 5: Weighted combination ──────────────────────────────────────────
    final_score = round(
        active_weights["momentum"]       * momentum
        + active_weights["trend"]          * trend
        + active_weights["trend_strength"] * trend_strength
        + active_weights["volatility"]     * volatility,
        4,
    )

    # ── Step 6: Dynamic threshold ─────────────────────────────────────────────
    dynamic_threshold = compute_dynamic_threshold(atr, latest_price)

    # ── Step 7: Disagreement penalty ──────────────────────────────────────────
    disagreement = compute_disagreement(momentum, trend, trend_strength)
    confidence = round(abs(final_score), 4)
    if disagreement:
        confidence = round(confidence * DISAGREEMENT_PENALTY, 4)

    # Clamp confidence to [0, 1]
    confidence = max(0.0, min(1.0, confidence))

    # ── Step 8: Signal decision ───────────────────────────────────────────────
    reasons: List[str] = []

    if final_score > dynamic_threshold:
        signal = BUY
        reasons.append(
            f"Score {final_score:.3f} exceeds dynamic BUY threshold ({dynamic_threshold:.3f})"
        )
    elif final_score < -dynamic_threshold:
        signal = SELL
        reasons.append(
            f"Score {final_score:.3f} below dynamic SELL threshold (-{dynamic_threshold:.3f})"
        )
    else:
        signal = HOLD
        reasons.append(
            f"Score {final_score:.3f} in neutral zone "
            f"[-{dynamic_threshold:.3f}, {dynamic_threshold:.3f}]"
        )

    # Regime explanation
    reasons.append(f"Regime: {regime} (divergence: {regime_metric:.4f})")

    # Factor-level explanations
    if abs(momentum) > 0.3:
        direction = "oversold (bullish)" if momentum > 0 else "overbought (bearish)"
        reasons.append(f"Momentum: RSI {rsi:.1f} -> {direction} (score: {momentum:+.3f})")

    if abs(trend) > 0.01:
        direction = "above" if trend > 0 else "below"
        reasons.append(
            f"Trend: price ${latest_price:,.2f} {direction} MA50 ${ma50:,.2f} (score: {trend:+.3f})"
        )

    if trend_strength != 0:
        label = "uptrend (MA50 > MA200)" if trend_strength > 0 else "downtrend (MA50 < MA200)"
        reasons.append(f"Trend strength: {label}")

    if disagreement:
        reasons.append("⚠ Factor disagreement detected — confidence reduced by 50%")

    # ── Structured logging ────────────────────────────────────────────────────
    log_data = {
        "symbol": symbol,
        "interval": interval,
        "price": latest_price,
        "rsi": rsi,
        "ma50": ma50,
        "ma200": ma200,
        "atr": atr,
        "regime": regime,
        "factors": {
            "momentum": momentum,
            "trend": trend,
            "trend_strength": trend_strength,
            "volatility": volatility,
        },
        "weights": active_weights,
        "final_score": final_score,
        "confidence": confidence,
        "threshold": dynamic_threshold,
        "disagreement": disagreement,
        "signal": signal,
    }
    logger.debug(json.dumps(log_data))

    return SignalResponse(
        symbol=symbol,
        interval=interval,
        signal=signal,
        score=final_score,
        confidence=confidence,
        regime=regime,
        threshold=dynamic_threshold,
        indicators=indicators,
        factors=factors,
        weights=weights_model,
        reason=reasons,
    )
