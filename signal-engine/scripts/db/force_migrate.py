import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def force_migrate():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["tradingbot"]
    col = db["prices"]
    
    print("Force migrating ALL records to 5m interval...")
    result = await col.update_many(
        {}, # Match ALL documents
        {"$set": {"interval": "5m"}}
    )
    print(f"Force updated {result.modified_count} records.")
    
    count = await col.count_documents({"symbol": "BTCUSDT", "interval": "5m"})
    print(f"Total BTCUSDT 5m records after migration: {count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(force_migrate())
