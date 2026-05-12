import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.tradingbot
    
    historical = await db.historical_1m_btcusdt.count_documents({})
    insights = await db.trade_insights.count_documents({})
    adaptations = await db.adaptation_results.count_documents({})
    
    print(f"Historical Candles: {historical}")
    print(f"Trades Executed: {insights}")
    print(f"AI Adaptations Generated: {adaptations}")

asyncio.run(run())
