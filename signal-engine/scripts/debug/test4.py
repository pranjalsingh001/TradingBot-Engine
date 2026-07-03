import asyncio
import motor.motor_asyncio
async def run():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.tradingbot
    
    # Check what timestamps exist exactly at Jan 15
    cursor = db.historical_1m_btcusdt.find({'timestamp': {'$gte': '2024-01-15T00:00:00+00:00'}}).sort("timestamp", 1)
    docs = await cursor.to_list(1)
    if docs:
        ts = docs[0]['timestamp']
        print("First doc on/after Jan 15 (+00:00 query):", ts)
        print("Comparison +00:00 < Z:", ts < "2024-01-15T00:00:00Z")
        print("Comparison +00:00 > Z:", ts > "2024-01-15T00:00:00Z")
    
    cursor2 = db.historical_1m_btcusdt.find({'timestamp': {'$gte': '2024-01-15T00:00:00Z'}}).sort("timestamp", 1)
    docs2 = await cursor2.to_list(1)
    if docs2:
        ts2 = docs2[0]['timestamp']
        print("First doc on/after Jan 15 (Z query):", ts2)
        
asyncio.run(run())
