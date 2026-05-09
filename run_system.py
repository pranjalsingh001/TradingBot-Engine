"""
run_system.py — Local Run Script for the Trading Application

Features:
- Live mode: starts the actual system background loop (not implemented fully here, but starts the loop).
- Simulation mode: Deterministically replays historical prices and streams them step-by-step
  into the system, mimicking a live environment.
"""

import argparse
import asyncio
import logging
import random
import pandas as pd
from datetime import datetime, timedelta, timezone

from app.trading.system_runner import TradingSystem

# Setup basic logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("Simulator")


def generate_mock_historical_data(symbol: str, total_candles: int) -> pd.DataFrame:
    """Generates synthetic price data to simulate different market conditions."""
    data = []
    base_price = 50000.0 if "BTC" in symbol else (3000.0 if "ETH" in symbol else 100.0)
    current_time = datetime.now(timezone.utc) - timedelta(minutes=5 * total_candles)
    
    # We will simulate a trending market first, then sideways, then volatile spike
    for i in range(total_candles):
        if i < total_candles * 0.4:
            # Trending UP
            base_price += random.uniform(5, 20)
        elif i < total_candles * 0.7:
            # Sideways
            base_price += random.uniform(-10, 10)
        else:
            # Volatile / Down
            base_price += random.uniform(-50, 40)
            
        data.append({
            "timestamp": current_time,
            "open": base_price,
            "high": base_price * 1.01,
            "low": base_price * 0.99,
            "close": base_price + random.uniform(-2, 2),
            "volume": 1000 + random.uniform(-100, 500)
        })
        current_time += timedelta(minutes=5)
        
    return pd.DataFrame(data)


async def run_simulation(steps: int):
    """
    Runs the deterministic simulation mode.
    Pre-generates data, then feeds it window-by-window into the trading loop.
    """
    logger.info(f"--- STARTING SIMULATION MODE ({steps} STEPS) ---")
    system = TradingSystem()
    # Reset to start fresh
    system.reset()
    
    symbols = system.loop.symbols
    
    # Generate 300 base candles + `steps` for the moving window
    total_needed = 300 + steps
    historical_data = {
        sym: generate_mock_historical_data(sym, total_needed) for sym in symbols
    }
    
    for i in range(steps):
        logger.info(f"--- SIMULATION STEP {i+1}/{steps} ---")
        window_end = 300 + i
        window_start = window_end - 250
        
        # Prepare the slice for this step
        step_data = {}
        for sym, df in historical_data.items():
            step_data[sym] = df.iloc[window_start:window_end].copy()
            
        # Feed exactly this window into the loop cycle
        await system.loop._execute_cycle(pre_fetched_data=step_data)
        
    # Output verification
    logger.info("--- SIMULATION COMPLETE ---")
    dashboard = system.get_dashboard()
    acc = dashboard["account"]
    
    logger.info(f"Final Balance:    ${acc['balance']:.2f}")
    logger.info(f"Final Equity:     ${acc['equity']:.2f}")
    logger.info(f"Max Drawdown:     {acc['drawdown']:.2f}%")
    logger.info(f"Total Trades:     {len(dashboard['recent_trades'])}")
    logger.info(f"Win Rate:         {acc['win_rate']*100:.1f}%")
    logger.info(f"Total Return:     {acc['total_return_pct']:.2f}%")
    
    if dashboard["positions"]:
        logger.info(f"Open Positions left: {len(dashboard['positions'])}")


async def main():
    parser = argparse.ArgumentParser(description="Trading System Local Runner")
    parser.add_argument("--mode", type=str, choices=["live", "simulation"], default="simulation", help="Run mode")
    parser.add_argument("--steps", type=int, default=100, help="Number of steps for simulation")
    
    args = parser.parse_args()
    
    if args.mode == "simulation":
        await run_simulation(args.steps)
    else:
        logger.info("Live mode selected. Starting background loop...")
        system = TradingSystem()
        await system.start()
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await system.stop()

if __name__ == "__main__":
    # Workaround for Windows asyncio event loop policy
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
