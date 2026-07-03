"""
replay_engine.py - Phase 2: Market Replay Engine
Simulates time passing by feeding historical candles to the TradingLoop.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.core.db import get_db

logger = logging.getLogger(__name__)

class ReplayState:
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.current_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.speed = 1.0  # multiplier, 0 = max speed
        self.interval = "1m"
        self.symbol = "BTCUSDT"

state = ReplayState()

async def get_all_historical_timestamps(symbol: str, interval: str, start_time: str, end_time: str):
    """Get a list of all timestamps to replay."""
    db = get_db()
    collection = db[f"historical_{interval}_{symbol.lower()}"]
    
    # Find timestamps starting from start_time
    cursor = collection.find(
        {"timestamp": {"$gte": start_time, "$lte": end_time}},
        {"timestamp": 1, "_id": 0}
    ).sort("timestamp", 1)
    
    docs = await cursor.to_list(length=None)
    return [d["timestamp"] for d in docs]

async def start_replay(loop, symbol: str, interval: str, start_time: str, end_time: str, speed: float = 1.0):
    """
    Start the replay engine.
    speed: 1.0 = real-time, 10.0 = 10x, 0.0 = max speed.
    """
    if state.is_running:
        logger.warning("[Replay] Engine is already running.")
        return
        
    state.is_running = True
    state.is_paused = False
    state.speed = speed
    state.symbol = symbol
    state.interval = interval
    state.end_time = datetime.fromisoformat(end_time)
    
    timestamps = await get_all_historical_timestamps(symbol, interval, start_time, end_time)
    if not timestamps:
        logger.error("[Replay] No historical data found for the given range.")
        state.is_running = False
        return
        
    logger.info(f"[Replay] Starting replay with {len(timestamps)} candles.")
    
    for ts in timestamps:
        while state.is_paused:
            await asyncio.sleep(0.1)
            if not state.is_running:
                break
                
        if not state.is_running:
            break
            
        state.current_time = datetime.fromisoformat(ts)
        
        await loop.execute_cycle(replay_timestamp=ts, historical=True, interval=interval)
        
        if state.speed > 0:
            # 1m = 60s. For 100x speed, sleep = 60 / 100 = 0.6s
            # This makes 1 minute of market time pass in 0.6s of real time.
            interval_map = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
            base_sec = interval_map.get(interval, 60)
            sleep_dur = base_sec / state.speed
            await asyncio.sleep(sleep_dur)
        else:
            # Max speed: minimal sleep to keep loop responsive
            await asyncio.sleep(0.001)

    state.is_running = False
    logger.info("[Replay] Engine finished.")

def pause_replay():
    state.is_paused = True

def resume_replay():
    state.is_paused = False

def stop_replay():
    state.is_running = False
    state.is_paused = False
