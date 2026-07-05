import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.collation import Collation

_client = None


def get_db_client():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URI"], tz_aware=True)
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

    await verify_transactions_supported()


async def verify_transactions_supported():
    try:
        client = get_db_client()
        db = get_db()
        async with await client.start_session() as session:
            async with session.start_transaction():
                await db.users.find_one({}, session=session)
        print("MongoDB transactions supported")
    except Exception as e:
        print(
            "MongoDB transactions unavailable — Mongo must run as a (single-node) "
            f"replica set; see README 'Mongo replica set' setup. Error: {e}"
        )
        raise


async def ensure_indexes():
    try:
        db = get_db()
        await db.users.create_index("email", unique=True)
        await db.users.create_index(
            "display_name", unique=True, collation=Collation(locale="en", strength=2)
        )
        await db.sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.articles.create_index("author_id")
        await db.purchases.create_index(
            [("buyer_id", 1), ("article_id", 1)], unique=True
        )
        await db.purchases.create_index("author_id")
        await db.purchases.create_index("article_id")
        await db.ledger.create_index("user_id")
        await db.ledger.create_index(
            "stripe_session_id",
            unique=True,
            partialFilterExpression={"stripe_session_id": {"$exists": True}},
        )
        await db.payout_requests.create_index("user_id")
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"MongoDB index creation failed: {e}")
        raise
