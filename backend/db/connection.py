import os
from motor.motor_asyncio import AsyncIOMotorClient

_client = None


def get_db_client():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _client


def get_db():
    return get_db_client()[os.environ["DB_NAME"]]


async def verify_db_connection():
    try:
        client = get_db_client()
        await client.admin.command("ping")
        print("MongoDB connected")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        raise


async def ensure_indexes():
    try:
        db = get_db()
        await db.users.create_index("email", unique=True)
        await db.sessions.create_index("expires_at", expireAfterSeconds=0)
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"MongoDB index creation failed: {e}")
        raise
