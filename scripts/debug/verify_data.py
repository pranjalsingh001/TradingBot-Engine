import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import pandas as pd
import json

async def verify():
    print("--- DATA VERIFICATION SCRIPT ---")
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["tradingbot"]
    col = db["prices"]
    
    print("1. Checking Total Count...")
    total = await col.count_documents({})
    print(f"Total documents in 'prices' collection: {total}")
    
    print("2. Checking symbols...")
    symbols = await col.distinct("symbol")
    print(f"Active symbols: {symbols}")
    
    print("3. Checking intervals...")
    intervals = await col.distinct("interval")
    print(f"Active intervals: {intervals}")
    
    print("4. Sample Data (Newest 5 for BTCUSDT)...")
    docs = await col.find({"symbol": "BTCUSDT"}).sort("timestamp", -1).limit(5).to_list(length=5)
    for d in docs:
        d["_id"] = str(d["_id"])
        print(json.dumps(d, indent=2))
        
    client.close()

if __name__ == "__main__":
    asyncio.run(verify())
