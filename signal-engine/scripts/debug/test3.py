import asyncio
import logging
from app.core.config import settings
from app.core.db import get_client
from app.trading.trading_loop import TradingLoop
from app.trading.paper_trading_engine import PaperAccount
from datetime import datetime, timezone

logging.basicConfig(level=logging.DEBUG)

async def test():
    get_client()
    account = PaperAccount()
    loop = TradingLoop(account)
    ts = "2024-01-01T12:00:00+00:00"
    try:
        await loop.execute_cycle(replay_timestamp=ts, historical=True, interval="1m")
        print("SUCCESS")
    except Exception as e:
        print("ERROR:", e)

asyncio.run(test())
