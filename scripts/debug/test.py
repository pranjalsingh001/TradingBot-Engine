import asyncio
import motor.motor_asyncio
async def run():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.tradingbot
    c = await db.historical_1m_btcusdt.count_documents({})
    print("TOTAL:", c)
    cursor = db.historical_1m_btcusdt.find({'timestamp': {'$gte': '2024-01-01T00:00:00Z', '$lte': '2024-02-01T00:00:00Z'}})
    docs = await cursor.to_list(10)
    print("WITH Z:", len(docs))
    cursor2 = db.historical_1m_btcusdt.find({'timestamp': {'$gte': '2024-01-01T00:00:00+00:00', '$lte': '2024-02-01T00:00:00+00:00'}})
    docs2 = await cursor2.to_list(10)
    print("WITH +00:00:", len(docs2))
asyncio.run(run())
