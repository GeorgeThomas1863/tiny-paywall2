import os
from motor.motor_asyncio import AsyncIOMotorClient

_client = None


def get_db_client():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _client


async def verify_db_connection():
    try:
        client = get_db_client()
        await client.admin.command("ping")
        print("MongoDB connected")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        raise
