import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def migrate_db():
    uri = "mongodb://localhost:27017"
    client = AsyncIOMotorClient(uri)
    db = client["tradingbot"]
    collection = db["prices"]
    
    print("Migrating existing price records...")
    # Update all documents that don't have an interval field
    result = await collection.update_many(
        {"interval": {"$exists": False}},
        {"$set": {"interval": "5m"}}
    )
    print(f"Updated {result.modified_count} records with interval='5m'")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate_db())
