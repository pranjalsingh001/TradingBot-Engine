import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

async def check():
    with open("test_db_output.txt", "w") as f:
        # USE 127.0.0.1 INSTEAD OF LOCALHOST
        client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
        db = client["tradingbot"]
        col = db["prices"]
        
        symbols = await col.distinct("symbol", {"interval": "5m"})
        f.write(f"Symbols with interval=5m: {symbols}\n")
        
        for sym in symbols:
            count = await col.count_documents({"symbol": sym, "interval": "5m"})
            f.write(f"{sym} count (5m): {count}\n")
        
        client.close()

if __name__ == "__main__":
    asyncio.run(check())
