import os

from dotenv import load_dotenv

load_dotenv()
os.environ["DB_NAME"] = f"{os.environ['DB_NAME']}_test"
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from db.connection import ensure_indexes, get_db
from main import app


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    await ensure_indexes()
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_collections():
    db = get_db()
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def make_client():
    clients = []

    async def create_client():
        new_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(new_client)
        return new_client

    yield create_client
    for open_client in clients:
        await open_client.aclose()
