"""
trading_loop.py — Production-safe async trading loop for the paper trading engine.

Stateful background task that:
    - Fetches latest prices / historical data
    - Runs the Signal Engine -> Risk Engine -> Portfolio Engine pipeline
    - Updates open positions and handles exits
    - Opens new trades
    - Persists state safely
    - Uses asyncio.Lock to prevent race conditions

Does NOT block the main event loop.
"""

import asyncio
import logging
import time
import traceback
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.btc_config import BTC_CONFIG
from app.core.schemas import RiskDecision
from app.core.models import PortfolioState, MarketSnapshot, Signal, SizedSignal
from app.trading.paper_trading_engine import PaperAccount
from app.engines.portfolio_engine import allocate_portfolio
from app.core.db import insert_trade_insight
from app.data.candle_loader import load_market_snapshot, compute_15m_bias
from app.engines.regime_engine_v2 import detect_regime_15m
from app.strategies.strategy_manager import StrategyManager
from app.risk.global_risk_controls import apply_risk, GlobalRiskControls

logger = logging.getLogger(__name__)

# Default symbols to trade
DEFAULT_SYMBOLS = [BTC_CONFIG["symbol"]]
DEFAULT_INTERVAL = BTC_CONFIG["default_interval"]


class TradingLoop:
    """
    Background trading loop manager.
    """

    def __init__(self, paper_account: PaperAccount):
        self.paper_account = paper_account
        self.running: bool = False
        self.task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()
        self.symbols = DEFAULT_SYMBOLS
        self.interval = DEFAULT_INTERVAL
        self.intervals = [DEFAULT_INTERVAL]
        self.recent_signals: List[dict] = []

    async def execute_cycle(self, replay_timestamp: str = None, historical: bool = False, interval: str = None):
        """
        Run a single iteration of the trading engine.
        """
        start_t = time.perf_counter()
        snapshots = await self.fetch_latest_data(replay_timestamp, historical)
        await self._execute_cycle(snapshots)

    async def fetch_latest_data(self, max_timestamp: str = None, historical: bool = False) -> Dict[str, MarketSnapshot]:
        """
        Fetches MarketSnapshots for all configured symbols.
        """
        snapshots = {}
        for sym in self.symbols:
            try:
                snapshot = await load_market_snapshot(
                    sym, 
                    max_timestamp=max_timestamp, 
                    historical=historical
                )
                if not snapshot.candles_15m.empty:
                    snapshot.regime = detect_regime_15m(snapshot.candles_15m)
                    snapshot.bias_15m = compute_15m_bias(snapshot.candles_15m)
                    snapshots[sym] = snapshot
            except Exception as e:
                logger.error(f"[Loop] Failed to fetch data for {sym}: {e}")
        return snapshots

    def extract_current_prices(self, snapshots: Dict[str, MarketSnapshot]) -> Dict[str, float]:
        """Extract the latest close price for each symbol from the 15m candles."""
        prices = {}
        for symbol, snapshot in snapshots.items():
            if not snapshot.candles_15m.empty:
                prices[symbol] = float(snapshot.candles_15m.iloc[-1]["close"])
        return prices

    async def start(self):
        """Start the background loop."""
        if self.running:
            logger.warning("[Loop] Already running, ignored start request.")
            return

        self.running = True
        self.paper_account.running = True
        self.paper_account.save_state()

        self.task = asyncio.create_task(self.run())
        logger.info("[Loop] Trading loop started.")

    async def stop(self):
        """Stop the background loop safely."""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

        self.paper_account.running = False
        self.paper_account.save_state()
        logger.info("[Loop] Trading loop stopped.")

    async def run(self):
        """Main asynchronous loop."""
        while self.running:
            async with self.lock:
                try:
                    await self._execute_cycle()
                except Exception as e:
                    logger.error("[Loop] Uncaught error in loop cycle: %s", e)
                    logger.debug(traceback.format_exc())
                    # DO NOT crash the loop

            # Wait before next iteration
            await asyncio.sleep(settings.paper_loop_interval)

    async def _execute_cycle(self, snapshots: Optional[Dict[str, MarketSnapshot]] = None):
        """Single execution cycle of the trading pipeline."""
        start_time = asyncio.get_event_loop().time()
        logger.info("[Loop] --- Starting cycle ---")

        # STEP 1: Fetch latest snapshots
        snapshots = snapshots if snapshots is not None else await self.fetch_latest_data()
        current_prices = self.extract_current_prices(snapshots)

        if not current_prices:
            logger.warning("[Loop] No price data available. Skipping cycle.")
            return

        # Update existing positions first (exits, trailing stops, PnL)
        closed_trades = self.paper_account.update_positions(current_prices)
        for trade in closed_trades:
            try:
                await insert_trade_insight(trade)
            except Exception as e:
                logger.error("[Loop] Failed to process closed trade: %s", e)

        # Build portfolio state for risk controls
        portfolio_state = PortfolioState(
            equity=self.paper_account.equity,
            peak_equity=self.paper_account.peak_balance,
            day_start_equity=self.paper_account.peak_balance,  # Simplified for now
            consecutive_losses=0,
            daily_drawdown_pct=self.paper_account.get_status().max_drawdown_pct,
            is_paused=not self.paper_account.running,
            recent_regimes=[]
        )

        risk_controls = GlobalRiskControls()
        strat_manager = StrategyManager()
        
        cycle_signals = []
        risk_decisions = []
        
        # STEP 2 & 3: Signal + Risk engines
        for symbol, snapshot in snapshots.items():
            try:
                # Select Strategy Based on Regime
                strategy = strat_manager.select(snapshot.regime)
                signal = strategy.evaluate(snapshot)
                
                # Apply Risk Controls
                sized_signal = apply_risk(signal, snapshot, portfolio_state, risk_controls)
                
                # Format for dashboard
                import math
                signal_data = {
                    "symbol": symbol,
                    "signal": signal.direction,
                    "confidence": 0.0 if math.isnan(signal.confidence) else signal.confidence,
                    "score": 0.0 if math.isnan(signal.confidence) else signal.confidence,
                    "regime": snapshot.regime,
                    "strategy_id": strategy.strategy_id,
                    "indicators": {"atr": 0.0 if math.isnan(snapshot.atr_5m) else snapshot.atr_5m, "rsi": 0.0},
                    "weights": {"trend": 0.33, "volatility": 0.33, "momentum": 0.33},
                    "risk_status": "ACCEPTED" if sized_signal else "REJECTED",
                    "risk_reason": "Risk limits passed" if sized_signal else "Risk limits failed or No Signal"
                }
                
                if sized_signal:
                    rd = RiskDecision(
                        symbol=symbol,
                        execute=True,
                        position_size=sized_signal.quantity,
                        stop_loss=sized_signal.sl,
                        take_profit=sized_signal.tp,
                        reason="Accepted by Risk Controls",
                        confidence=signal.confidence,
                        signal=signal.direction
                    )
                    risk_decisions.append(rd)
                    signal_data["quantity"] = sized_signal.quantity
                    signal_data["sl"] = sized_signal.sl
                    signal_data["tp"] = sized_signal.tp
                    signal_data["dollar_risk"] = sized_signal.dollar_risk

                cycle_signals.append(signal_data)
                
            except Exception as e:
                logger.error("[Loop] Error processing %s: %s", symbol, e)
                
        self.recent_signals = cycle_signals

        # STEP 4: Portfolio Engine
        portfolio_decision = allocate_portfolio(
            risk_decisions,
            balance=self.paper_account.balance
        )

        # STEP 5: Open new trades
        opened_count = 0
        for trade in portfolio_decision.selected_trades:
            if self.paper_account.has_position(trade.symbol):
                continue

            risk_info = next((r for r in risk_decisions if r.symbol == trade.symbol), None)
            signal_data = next((s for s in cycle_signals if s.get("symbol") == trade.symbol), None)
            
            entry_metadata = {
                "regime": signal_data["regime"] if signal_data else "UNKNOWN",
                "strategy_id": signal_data["strategy_id"] if signal_data else "UNKNOWN"
            }

            pos = self.paper_account.open_position(
                symbol=trade.symbol,
                side=trade.signal,
                entry_price=current_prices.get(trade.symbol, 0.0),
                position_size=trade.position_size,
                stop_loss=risk_info.stop_loss,
                take_profit=risk_info.take_profit,
                entry_metadata=entry_metadata
            )
            if pos:
                opened_count += 1

        # STEP 6: Save state
        self.paper_account.save_state()

        duration = asyncio.get_event_loop().time() - start_time
        logger.info(
            "[Loop] Cycle complete in %.2fs | Candidates: %d | "
            "Opened: %d | Closed: %d | Equity: $%.2f",
            duration, len(risk_decisions), opened_count,
            len(closed_trades), self.paper_account.equity
        )

        # STEP 7: Adaptive Learning
        # Periodically trigger AI recommendations if trades were closed
        if closed_trades:
            try:
                from app.engines.analytics_engine import get_performance_metrics
                from app.engines.ai_recommender import generate_recommendations
                from app.engines.validation_engine import validate_recommendation
                from app.core.db import save_adaptation_result

                analytics = await get_performance_metrics()
                recs = await generate_recommendations(analytics)
                for rec in recs:
                    valid_rec = validate_recommendation(rec, analytics, {})
                    
                    # Save to adaptation_results for history/walk-forward
                    await save_adaptation_result(valid_rec)
                    
                    if valid_rec["status"] == "APPROVED":
                        # Save to recommendations for the engine to pick up
                        from app.core.db import save_recommendation
                        await save_recommendation(valid_rec)
                        
                        # Trigger reload in adaptive_config
                        from app.core.adaptive_config import load_approved_profiles
                        await load_approved_profiles()
                        
                        logger.info(f"[Loop] Applied NEW intelligence for regime {valid_rec.get('target_regime')}")
            except Exception as e:
                logger.error(f"[Loop] Adaptive learning error: {e}")
