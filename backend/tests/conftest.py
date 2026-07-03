import os

from dotenv import load_dotenv

load_dotenv()
os.environ["DB_NAME"] = f"{os.environ['DB_NAME']}_test"

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
