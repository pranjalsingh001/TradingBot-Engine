"""
risk_engine.py — Consistent risk-controlled trading engine.

Position sizing is based on stop-loss distance, not fixed percentages.
Every trade risks the same dollar amount regardless of volatility.

Pipeline:
    1. Run risk filters (signal, confidence, volatility, trades, drawdown, exposure, correlation)
    2. Compute ATR-based stop loss & take profit
    3. Size position from stop distance (risk_amount / stop_distance)
    4. Apply confidence modifier
    5. Validate risk consistency
    6. Compute trailing stop levels

Single responsibility: risk management only.
No DB calls. No HTTP. No randomness. No order execution.
"""

import logging
from typing import List, Tuple

from app.core.config import settings
from app.core.schemas import (
    SignalResponse, AccountState, RiskDecision, TrailingStopLevels,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
BUY  = "BUY"
SELL = "SELL"
HOLD = "HOLD"


# ── Risk filters (pure functions) ─────────────────────────────────────────────

def check_signal_actionable(signal: str) -> Tuple[bool, str]:
    """Filter 1: Only BUY/SELL signals are actionable."""
    if signal == HOLD:
        return False, "Signal is HOLD — no action"
    return True, ""


def check_confidence(confidence: float) -> Tuple[bool, str]:
    """Filter 2: Reject low-confidence signals."""
    if confidence < settings.min_confidence:
        return False, (
            f"Confidence {confidence:.3f} below minimum threshold "
            f"({settings.min_confidence})"
        )
    return True, ""


def check_volatility(atr: float, price: float) -> Tuple[bool, str]:
    """Filter 3: Reject trades in excessively volatile markets."""
    if price == 0:
        return False, "Price is zero — cannot assess volatility"
    vol_ratio = atr / price
    if vol_ratio > settings.max_volatility_ratio:
        return False, (
            f"Volatility too high: ATR/price = {vol_ratio:.4f} "
            f"exceeds max ({settings.max_volatility_ratio})"
        )
    return True, ""


def check_active_trades(active_trades: int) -> Tuple[bool, str]:
    """Filter 4: Enforce portfolio-level trade cap."""
    if active_trades >= settings.max_active_trades:
        return False, (
            f"Max active trades reached: {active_trades}/{settings.max_active_trades}"
        )
    return True, ""


def check_drawdown(balance: float, peak_balance: float) -> Tuple[bool, str]:
    """Filter 5: Circuit breaker — stop trading on excessive drawdown."""
    if peak_balance <= 0:
        return False, "Invalid peak balance"
    drawdown = (peak_balance - balance) / peak_balance
    if drawdown >= settings.max_drawdown_pct:
        return False, (
            f"Circuit breaker: drawdown {drawdown:.1%} "
            f"exceeds max ({settings.max_drawdown_pct:.0%})"
        )
    return True, ""


def check_portfolio_exposure(
    current_exposure: float, new_position_size: float, balance: float,
) -> Tuple[bool, str]:
    """Filter 6: Total portfolio exposure must stay ≤ 30% of balance."""
    max_exposure = balance * settings.max_portfolio_exposure
    exposure_after = current_exposure + new_position_size
    if exposure_after > max_exposure:
        return False, (
            f"Portfolio exposure would be ${exposure_after:,.2f} "
            f"(>{settings.max_portfolio_exposure:.0%} of ${balance:,.2f} = ${max_exposure:,.2f})"
        )
    return True, ""


def check_correlation(symbol: str, open_symbols: List[str]) -> Tuple[bool, str]:
    """Filter 7: Block duplicate symbol positions."""
    if symbol in open_symbols:
        return False, (
            f"Duplicate symbol blocked: {symbol} already has an open position"
        )
    return True, ""


# ── Stop loss & take profit ──────────────────────────────────────────────────

def compute_stop_loss(
    entry_price: float, atr: float, signal: str,
) -> float:
    """
    ATR-based stop loss.

    BUY:  stop = entry - (ATR * multiplier)
    SELL: stop = entry + (ATR * multiplier)
    """
    stop_distance = atr * settings.atr_stop_multiplier

    if signal == BUY:
        return round(max(0.0, entry_price - stop_distance), 4)
    elif signal == SELL:
        return round(entry_price + stop_distance, 4)
    return 0.0


def compute_take_profit(
    entry_price: float, atr: float, signal: str,
) -> float:
    """
    Take profit based on risk-reward ratio.

    BUY:  tp = entry + (stop_distance * rr_ratio)
    SELL: tp = entry - (stop_distance * rr_ratio)
    """
    stop_distance = atr * settings.atr_stop_multiplier
    tp_distance = stop_distance * settings.risk_reward_ratio

    if signal == BUY:
        return round(entry_price + tp_distance, 4)
    elif signal == SELL:
        return round(max(0.0, entry_price - tp_distance), 4)
    return 0.0


def compute_stop_loss_distance(
    entry_price: float, stop_loss: float,
) -> float:
    """Absolute distance between entry and stop loss."""
    return round(abs(entry_price - stop_loss), 4)


# ── Position sizing (risk-based) ─────────────────────────────────────────────

def compute_position_size(
    balance: float,
    stop_loss_distance: float,
    confidence: float,
) -> float:
    """
    Professional risk-based position sizing.

    Steps:
        1. risk_amount = balance × max_risk_per_trade
        2. position_size = risk_amount / stop_loss_distance
        3. position_size *= confidence (modifier)
        4. Cap at balance × max_position_pct

    Large stop -> smaller position.
    Small stop -> larger position.
    Same risk dollar amount every trade.
    """
    if stop_loss_distance <= 0:
        return 0.0

    risk_amount = balance * settings.max_risk_per_trade
    position_size = risk_amount / stop_loss_distance

    # Confidence modifier
    position_size *= confidence

    # Cap
    max_position = balance * settings.max_position_pct
    position_size = min(position_size, max_position)

    return round(position_size, 4)


def compute_position_units(
    position_size: float, entry_price: float,
) -> float:
    """Convert position size (currency) to units at entry price."""
    if entry_price <= 0:
        return 0.0
    return round(position_size / entry_price, 6)


def validate_risk_consistency(
    position_size: float, stop_loss_distance: float, balance: float,
) -> float:
    """
    Validate that actual risk ≤ risk_amount.
    Returns the actual risk in currency.
    """
    risk_amount = balance * settings.max_risk_per_trade
    actual_risk = position_size * stop_loss_distance
    # Should never exceed, but clamp if floating point drift
    if actual_risk > risk_amount * 1.001:  # 0.1% tolerance
        logger.warning(
            "[Risk] Risk inconsistency: actual=%.2f > limit=%.2f",
            actual_risk, risk_amount,
        )
    return round(min(actual_risk, risk_amount), 4)


# ── Trailing stops ───────────────────────────────────────────────────────────

def compute_trailing_stops(
    entry_price: float, atr: float, signal: str,
) -> TrailingStopLevels:
    """
    Compute trailing stop trigger levels.

    At 1R profit -> move stop to breakeven (entry price)
    At 2R profit -> trail stop to lock 1R

    R = stop_loss_distance = ATR * multiplier
    """
    stop_distance = atr * settings.atr_stop_multiplier

    if signal == BUY:
        breakeven_trigger = round(entry_price + stop_distance, 4)       # 1R profit
        trail_trigger = round(entry_price + stop_distance * 2, 4)       # 2R profit
        breakeven_stop = entry_price                                     # move to entry
        trail_stop = round(entry_price + stop_distance, 4)              # lock 1R
    elif signal == SELL:
        breakeven_trigger = round(entry_price - stop_distance, 4)       # 1R profit
        trail_trigger = round(max(0.0, entry_price - stop_distance * 2), 4)  # 2R profit
        breakeven_stop = entry_price
        trail_stop = round(entry_price - stop_distance, 4)              # lock 1R
    else:
        return TrailingStopLevels(
            breakeven_trigger=0.0, trail_trigger=0.0,
            breakeven_stop=0.0, trail_stop=0.0,
        )

    return TrailingStopLevels(
        breakeven_trigger=breakeven_trigger,
        trail_trigger=trail_trigger,
        breakeven_stop=breakeven_stop,
        trail_stop=trail_stop,
    )


# ── Core risk engine ──────────────────────────────────────────────────────────

def evaluate_risk(
    signal_result: SignalResponse,
    account: AccountState,
) -> RiskDecision:
    """
    Core risk evaluation function.

    Pipeline:
        1. Run all risk filters
        2. Compute stop loss & take profit
        3. Compute risk-based position size (risk_amount / stop_distance)
        4. Validate portfolio exposure
        5. Validate risk consistency
        6. Compute trailing stop levels
        7. Return execution decision

    Parameters
    ----------
    signal_result : SignalResponse  output from the signal engine
    account       : AccountState    current account state

    Returns
    -------
    RiskDecision — execute or skip with full details
    """
    symbol = signal_result.symbol
    interval = signal_result.interval
    signal = signal_result.signal
    confidence = signal_result.confidence
    price = signal_result.indicators.price
    atr = signal_result.indicators.atr
    regime = signal_result.regime

    # ── Base rejection template ───────────────────────────────────────────────
    def _reject(reason: str) -> RiskDecision:
        logger.info("[Risk] %s (%s) SKIP: %s", symbol, interval, reason)
        return RiskDecision(
            execute=False,
            reason=reason,
            signal=signal,
            symbol=symbol,
            interval=interval,
            entry_price=price,
            confidence=confidence,
            regime=regime,
        )

    # ── Filter 1: Signal type ─────────────────────────────────────────────────
    ok, reason = check_signal_actionable(signal)
    if not ok:
        return _reject(reason)

    # ── Filter 2: Confidence ──────────────────────────────────────────────────
    ok, reason = check_confidence(confidence)
    if not ok:
        return _reject(reason)

    # ── Filter 3: Volatility ─────────────────────────────────────────────────
    ok, reason = check_volatility(atr, price)
    if not ok:
        return _reject(reason)

    # ── Filter 4: Active trades ──────────────────────────────────────────────
    ok, reason = check_active_trades(account.active_trades)
    if not ok:
        return _reject(reason)

    # ── Filter 5: Drawdown circuit breaker ───────────────────────────────────
    ok, reason = check_drawdown(account.balance, account.peak_balance)
    if not ok:
        return _reject(reason)

    # ── Filter 6: Correlation (duplicate symbol) ─────────────────────────────
    ok, reason = check_correlation(symbol, account.open_symbols)
    if not ok:
        return _reject(reason)

    # ── Compute stop loss & take profit ──────────────────────────────────────
    stop_loss = compute_stop_loss(price, atr, signal)
    take_profit = compute_take_profit(price, atr, signal)
    sl_distance = compute_stop_loss_distance(price, stop_loss)

    if sl_distance <= 0:
        return _reject("Stop loss distance is zero — cannot size position")

    # ── Risk-based position sizing ───────────────────────────────────────────
    position_size = compute_position_size(
        account.balance, sl_distance, confidence,
    )

    # ── Filter 7: Portfolio exposure ─────────────────────────────────────────
    ok, reason = check_portfolio_exposure(
        account.current_exposure, position_size, account.balance,
    )
    if not ok:
        return _reject(reason)

    # ── Risk consistency validation ──────────────────────────────────────────
    risk_amount = validate_risk_consistency(
        position_size, sl_distance, account.balance,
    )

    position_units = compute_position_units(position_size, price)
    exposure_after = round(account.current_exposure + position_size, 4)

    # ── Trailing stops ───────────────────────────────────────────────────────
    trailing_stops = compute_trailing_stops(price, atr, signal)

    reason = (
        f"{signal} signal accepted | confidence={confidence:.3f} | "
        f"regime={regime} | position=${position_size:,.2f} | "
        f"risk=${risk_amount:,.2f}"
    )
    logger.info("[Risk] %s (%s) EXECUTE: %s", symbol, interval, reason)

    return RiskDecision(
        execute=True,
        reason=reason,
        signal=signal,
        symbol=symbol,
        interval=interval,
        position_size=position_size,
        position_units=position_units,
        entry_price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=settings.risk_reward_ratio,
        risk_amount=risk_amount,
        stop_loss_distance=sl_distance,
        exposure_after_trade=exposure_after,
        confidence=confidence,
        regime=regime,
        trailing_stops=trailing_stops,
    )
