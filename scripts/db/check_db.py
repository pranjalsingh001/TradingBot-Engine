import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def check_db():
    uri = "mongodb://localhost:27017"
    client = AsyncIOMotorClient(uri)
    db = client["tradingbot"]
    collection = db["prices"]
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    interval = "5m"
    
    for symbol in symbols:
        count = await collection.count_documents({"symbol": symbol, "interval": interval})
        print(f"Symbol: {symbol}, Interval: {interval}, Count: {count}")
        
        if count > 0:
            latest = await collection.find({"symbol": symbol, "interval": interval}).sort("timestamp", -1).limit(1).to_list(1)
            print(f"  Latest: {latest[0]['timestamp']} at price {latest[0]['price']}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check_db())
