"""
historical_loader.py - Phase 1: Historical Data Infrastructure
Fetches historical Klines from Binance and stores them sequentially.
"""
import asyncio
import logging
import httpx
from typing import List, Dict, Any
from datetime import datetime, timezone
import motor.motor_asyncio
from pymongo import UpdateOne
from app.core.db import get_db

logger = logging.getLogger(__name__)

BINANCE_API_URL = "https://api.binance.com/api/v3/klines"

async def fetch_klines(symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch klines from Binance API."""
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(BINANCE_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        candles = []
        for row in data:
            candles.append({
                "timestamp": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).isoformat(),
                "price": float(row[4]), # map close to price for signal engine compatibility
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5])
            })
        return candles

async def load_historical_data(symbol: str, interval: str, start_date: str, end_date: str):
    """
    Load historical data for a specific symbol, interval, and date range.
    Store into historical_{interval} collection.
    """
    start_ts = int(datetime.fromisoformat(start_date).timestamp() * 1000)
    end_ts = int(datetime.fromisoformat(end_date).timestamp() * 1000)
    
    collection_name = f"historical_{interval}_{symbol.lower()}"
    db = get_db()
    collection = db[collection_name]
    
    # Ensure unique index on timestamp
    await collection.create_index("timestamp", unique=True)
    
    current_start = start_ts
    total_inserted = 0
    
    logger.info(f"Starting historical load for {symbol} {interval} from {start_date} to {end_date}")
    
    while current_start < end_ts:
        try:
            candles = await fetch_klines(symbol, interval, current_start, end_ts)
            if not candles:
                break
                
            operations = [
                UpdateOne(
                    {"timestamp": c["timestamp"]},
                    {"$setOnInsert": c},
                    upsert=True
                )
                for c in candles
            ]
            
            if operations:
                result = await collection.bulk_write(operations, ordered=False)
                inserted = result.upserted_count
                total_inserted += inserted
            else:
                inserted = 0
                
            # Update current_start to the last candle's timestamp + 1ms to fetch next batch
            last_ts = int(datetime.fromisoformat(candles[-1]["timestamp"]).timestamp() * 1000)
            current_start = last_ts + 1
            
            logger.info(f"Loaded batch up to {candles[-1]['timestamp']}. Inserted {inserted} new candles.")
            
            # Rate limiting
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            await asyncio.sleep(5)
            
    logger.info(f"Historical load complete. Total new candles inserted: {total_inserted}")

if __name__ == "__main__":
    from app.core.db import get_client
    logging.basicConfig(level=logging.INFO)
    
    async def run():
        get_client()
        await load_historical_data("BTCUSDT", "1m", "2024-01-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00")
        
    asyncio.run(run())
