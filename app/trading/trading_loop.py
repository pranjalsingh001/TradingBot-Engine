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
from app.trading.paper_trading_engine import PaperAccount
from app.engines.signal_engine import generate_signal
from app.engines.risk_engine import evaluate_risk
from app.engines.portfolio_engine import allocate_portfolio
from app.core.db import fetch_prices, insert_trade_insight

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
        
        # ── Step 1: Ingest Data ──
        # Fetch prices across all assets/intervals for this cycle.
        
        data = {}
        use_interval = interval or self.interval
        for sym in self.symbols:
            # Replay currently supports evaluating a single primary interval (e.g. 1m)
            df = await fetch_prices(sym, use_interval, max_timestamp=replay_timestamp, historical=historical)
            if df is not None and not df.empty:
                data[sym] = df
        
        await self._execute_cycle(data, interval=use_interval)

    async def fetch_latest_data(self) -> Dict[str, object]:
        """
        Abstracted data fetching.
        Returns a dict of dataframes keyed by symbol.
        Make it pluggable for future real APIs.
        """
        data = {}
        for symbol in self.symbols:
            try:
                df = await fetch_prices(
                    symbol,
                    interval=self.interval,
                    limit=settings.default_candle_limit
                )
                if df is not None and not df.empty:
                    logger.info("[Loop] Fetched %d records for %s", len(df), symbol)
                    data[symbol] = df
                else:
                    logger.warning("[Loop] No data returned for %s (interval=%s)", symbol, self.interval)
            except Exception as e:
                logger.warning("[Loop] Failed to fetch data for %s: %s", symbol, e)
        print(f"DEBUG: Data Fetch Cycle Complete. Symbols with data: {list(data.keys())}")
        return data

    def extract_current_prices(self, data: Dict[str, object]) -> Dict[str, float]:
        """Extract the latest close price for each symbol."""
        prices = {}
        for symbol, df in data.items():
            if not df.empty:
                prices[symbol] = float(df.iloc[-1]["price"])
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

    async def _execute_cycle(self, pre_fetched_data: Optional[Dict[str, object]] = None, interval: str = None):
        """Single execution cycle of the trading pipeline."""
        use_interval = interval or self.interval
        start_time = asyncio.get_event_loop().time()
        logger.info("[Loop] --- Starting cycle ---")

        # STEP 1: Fetch latest prices/data (unless provided by simulation)
        data = pre_fetched_data if pre_fetched_data is not None else await self.fetch_latest_data()
        current_prices = self.extract_current_prices(data)

        if not current_prices:
            logger.warning("[Loop] No price data available. Skipping cycle.")
            return

        # Update existing positions first (exits, trailing stops, PnL)
        closed_trades = self.paper_account.update_positions(current_prices)
        for trade in closed_trades:
            try:
                await insert_trade_insight(trade)
            except Exception as e:
                logger.error("[Loop] Failed to insert trade insight: %s", e)

        # STEP 2 & 3: Signal + Risk engines
        risk_decisions: List[RiskDecision] = []
        cycle_signals = []
        
        for symbol, df in data.items():
            try:
                signal_res = generate_signal(df, symbol, use_interval)
                
                # Check for ErrorResponse (from schemas import ErrorResponse)
                from app.core.schemas import ErrorResponse, AccountState
                if isinstance(signal_res, ErrorResponse):
                    signal_data = signal_res.model_dump()
                    signal_data["risk_status"] = "ERROR"
                    signal_data["risk_reason"] = signal_res.error
                    cycle_signals.append(signal_data)
                    continue

                account_state = AccountState(
                    balance=self.paper_account.balance,
                    peak_balance=self.paper_account.peak_balance,
                    active_trades=len(self.paper_account.open_positions),
                    current_exposure=sum(p.position_size for p in self.paper_account.open_positions.values()),
                    open_symbols=list(self.paper_account.open_positions.keys())
                )

                risk_res = evaluate_risk(signal_res, account_state)
                
                # Update the signal object with risk info for the dashboard
                signal_data = signal_res.model_dump()
                signal_data["risk_status"] = "ACCEPTED" if risk_res.execute else "REJECTED"
                signal_data["risk_reason"] = risk_res.reason
                cycle_signals.append(signal_data)
                
                if risk_res.execute:
                    risk_decisions.append(risk_res)
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
            # Re-verify we don't have it (defense in depth)
            if self.paper_account.has_position(trade.symbol):
                continue

            risk_info = next((r for r in risk_decisions if r.symbol == trade.symbol), None)
            if not risk_info:
                continue

            signal_data = next((s for s in cycle_signals if s.get("symbol") == trade.symbol), None)
            entry_metadata = {}
            if signal_data:
                entry_metadata = {
                    "rsi": signal_data.get("indicators", {}).get("rsi", 0.0),
                    "atr": signal_data.get("indicators", {}).get("atr", 0.0),
                    "confidence": signal_data.get("confidence", 0.0),
                    "regime": signal_data.get("regime", ""),
                    "weights": signal_data.get("weights", {})
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
