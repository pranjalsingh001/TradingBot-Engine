"""
db.py — Async MongoDB data access layer using Motor.

Responsibility: Fetch the last N price records for a given symbol,
sorted ascending by timestamp, so indicators can be computed left-to-right.
"""

import logging
from typing import List, Optional, Any

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

import os
from unittest.mock import AsyncMock

# ── Motor client — created once, reused across all requests ──────────────────
_client: Optional[Any] = None

def get_client() -> Any:
    global _client
    if os.getenv("TESTING") == "1":
        return AsyncMock()

    if _client is None:
        # pyrefly: ignore [missing-import]
        import motor.motor_asyncio
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5000,
        )
        logger.info("[DB] Motor client initialised")
    return _client

def get_db() -> Any:
    return get_client()[settings.mongo_db]

def get_collection() -> Any:
    if os.getenv("TESTING") == "1":
        return AsyncMock()
    return get_db()[settings.mongo_collection]


async def fetch_prices(symbol: str, interval: str, limit: int = settings.default_candle_limit, max_timestamp: Optional[str] = None, historical: bool = False) -> pd.DataFrame:
    """
    Fetch the latest `limit` price records for `symbol`, sorted ASC by timestamp.
    If historical is True, fetches from historical_{interval}_{symbol.lower()}
    """
    db = get_db()
    symbol = symbol.upper()
    collection_name = f"historical_{interval}_{symbol.lower()}" if historical else settings.mongo_collection
    collection = db[collection_name]

    query = {"symbol": symbol, "interval": interval} if not historical else {}
    if max_timestamp:
        query["timestamp"] = {"$lte": max_timestamp}

    cursor = (
        collection
        .find(
            query,
            {"_id": 0, "symbol": 1, "price": 1, "timestamp": 1, "interval": 1, "open": 1, "high": 1, "low": 1, "volume": 1}
        )
        .sort("timestamp", -1)
        .limit(limit)
    )

    docs = await cursor.to_list(length=limit)

    if not docs:
        logger.warning("[DB] No documents found for symbol=%s", symbol)
        return pd.DataFrame()

    df = pd.DataFrame(docs)

    # Sort ascending — indicators must be computed left-to-right (oldest -> newest)
    df.sort_values("timestamp", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Ensure price is numeric — guard against any string leakage
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df.dropna(subset=["price", "timestamp"], inplace=True)

    logger.info("[DB] Fetched %d records for %s", len(df), symbol)
    return df


async def fetch_prices_bulk(
    symbol: str, interval: str, limit: int = 1000
) -> pd.DataFrame:
    """
    Fetch a large set of historical price records for backtesting.

    Same logic as fetch_prices but with a higher default limit
    and no dependency on default_candle_limit config.

    Parameters
    ----------
    symbol   : str   e.g. "BTCUSDT"
    interval : str   e.g. "5m", "1h"
    limit    : int   number of records to pull (default: 1000)
    """
    collection = get_collection()
    symbol = symbol.upper()

    cursor = (
        collection
        .find(
            {"symbol": symbol, "interval": interval},
            {"_id": 0, "symbol": 1, "price": 1, "timestamp": 1, "interval": 1, "open": 1, "high": 1, "low": 1, "volume": 1}
        )
        .sort("timestamp", -1)
        .limit(limit)
    )

    docs = await cursor.to_list(length=limit)

    if not docs:
        logger.warning("[DB] No documents found for symbol=%s interval=%s (bulk)", symbol, interval)
        return pd.DataFrame()

    df = pd.DataFrame(docs)
    df.sort_values("timestamp", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df.dropna(subset=["price", "timestamp"], inplace=True)

    logger.info("[DB] Bulk fetched %d records for %s (%s)", len(df), symbol, interval)
    return df


async def close_connection():
    """Cleanly close the Motor client on app shutdown."""
    global _client
    if _client is not None:
        _client.close()
        logger.info("[DB] Motor client closed")


async def insert_trade_insight(trade_log) -> None:
    """Insert a TradeInsight into the database (Phase 2)."""
    collection = get_db()["trade_insights"]
    
    # Calculate duration
    try:
        from datetime import datetime, timezone
        opened = datetime.fromisoformat(trade_log.opened_at)
        closed = datetime.fromisoformat(trade_log.closed_at)
        duration = int((closed - opened).total_seconds() / 60)
    except Exception:
        duration = 0
        
    insight = {
        "trade_id": f"{trade_log.symbol}_{int(datetime.now(timezone.utc).timestamp())}",
        "symbol": trade_log.symbol,
        "entry_price": trade_log.entry_price,
        "exit_price": trade_log.exit_price,
        "result": "WIN" if trade_log.profit > 0 else "LOSS",
        "profit_percent": trade_log.return_pct,
        "market_regime": trade_log.entry_metadata.get("regime", "UNKNOWN"),
        "rsi": trade_log.entry_metadata.get("rsi", 0.0),
        "macd": 0.0,
        "atr": trade_log.entry_metadata.get("atr", 0.0),
        "confidence": trade_log.entry_metadata.get("confidence", 0.0),
        "weights": trade_log.entry_metadata.get("weights", {}),
        "trade_duration_minutes": duration,
        "timestamp": trade_log.closed_at
    }
    
    try:
        await collection.insert_one(insight)
        logger.info("[DB] Inserted trade insight for %s", trade_log.symbol)
    except Exception as e:
        logger.error("[DB] Failed to insert trade insight: %s", e)

async def save_recommendation(rec: dict) -> None:
    collection = get_db()["recommendations"]
    try:
        await collection.update_one(
            {"recommendation_id": rec["recommendation_id"]},
            {"$set": rec},
            upsert=True
        )
        logger.info("[DB] Saved AI recommendation %s", rec["recommendation_id"])
    except Exception as e:
        logger.error("[DB] Failed to save recommendation: %s", e)

async def save_adaptation_result(result: dict) -> None:
    collection = get_db()["adaptation_results"]
    try:
        await collection.update_one(
            {"recommendation_id": result["recommendation_id"]},
            {"$set": result},
            upsert=True
        )
        logger.info("[DB] Saved adaptation result for %s", result["recommendation_id"])
    except Exception as e:
        logger.error("[DB] Failed to save adaptation result: %s", e)
