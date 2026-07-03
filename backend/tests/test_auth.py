from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

from db.connection import get_db

ALICE = {"email": "alice@test.com", "password": "password123", "display_name": "Alice"}
BOB = {"email": "bob@test.com", "password": "password456", "display_name": "Bob"}


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from auth.rate_limit import reset_attempts

    reset_attempts()


#--- register ---

async def test_register_creates_account_and_session(client):
    response = await client.post("/auth/register", json=ALICE)

    assert response.status_code == 200
    assert response.json()["success"] is True

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "email": "alice@test.com",
        "display_name": "Alice",
        "is_admin": False,
        "wallet_cents": 0,
        "earnings_cents": 0,
    }


async def test_register_normalizes_email(client):
    payload = {**ALICE, "email": "  ALICE@Test.COM "}
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 200
    me = await client.get("/auth/me")
    assert me.json()["email"] == "alice@test.com"


async def test_register_duplicate_email_409(client):
    await client.post("/auth/register", json=ALICE)

    payload = {**BOB, "email": ALICE["email"]}
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 409
    assert "email" in response.json()["detail"].lower()


async def test_register_duplicate_display_name_case_insensitive_409(client):
    await client.post("/auth/register", json=ALICE)

    payload = {**BOB, "display_name": "aLiCe"}
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 409
    assert "name" in response.json()["detail"].lower()


async def test_register_invalid_email_422(client):
    response = await client.post("/auth/register", json={**ALICE, "email": "not-an-email"})

    assert response.status_code == 422


async def test_register_short_password_422(client):
    response = await client.post("/auth/register", json={**ALICE, "password": "short7!"})

    assert response.status_code == 422


async def test_register_empty_display_name_422(client):
    response = await client.post("/auth/register", json={**ALICE, "display_name": "   "})

    assert response.status_code == 422


async def test_password_stored_as_bcrypt_hash(client):
    await client.post("/auth/register", json=ALICE)

    user = await get_db().users.find_one({"email": ALICE["email"]})
    assert user["password_hash"].startswith("$2")
    assert user["password_hash"] != ALICE["password"]
    assert bcrypt.checkpw(ALICE["password"].encode(), user["password_hash"].encode())


#--- login / logout ---

async def test_login_success(client):
    await client.post("/auth/register", json=ALICE)
    await client.post("/auth/logout")

    response = await client.post(
        "/auth/login", json={"email": ALICE["email"], "password": ALICE["password"]}
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    me = await client.get("/auth/me")
    assert me.json()["display_name"] == "Alice"


async def test_login_unknown_email_and_wrong_password_are_identical(client):
    await client.post("/auth/register", json=ALICE)
    await client.post("/auth/logout")

    wrong_password = await client.post(
        "/auth/login", json={"email": ALICE["email"], "password": "wrongpassword"}
    )
    unknown_email = await client.post(
        "/auth/login", json={"email": "ghost@test.com", "password": "wrongpassword"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_logout_kills_session(client):
    await client.post("/auth/register", json=ALICE)

    response = await client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert await get_db().sessions.find_one({}) is None

    me = await client.get("/auth/me")
    assert me.status_code == 401


async def test_me_requires_auth(client):
    response = await client.get("/auth/me")

    assert response.status_code == 401


#--- rate limiting ---

async def test_login_rate_limited_after_10_failures(client):
    await client.post("/auth/register", json=ALICE)
    await client.post("/auth/logout")

    for _ in range(10):
        response = await client.post(
            "/auth/login", json={"email": ALICE["email"], "password": "wrongpassword"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/auth/login", json={"email": ALICE["email"], "password": ALICE["password"]}
    )
    assert response.status_code == 429


#--- sessions ---

async def test_session_expires_in_30_days(client):
    await client.post("/auth/register", json=ALICE)

    session = await get_db().sessions.find_one({})
    lifetime = session["expires_at"] - session["created_at"]
    assert timedelta(days=29, hours=23) < lifetime < timedelta(days=30, hours=1)


async def test_expired_session_rejected(client):
    await client.post("/auth/register", json=ALICE)

    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    await get_db().sessions.update_many({}, {"$set": {"expires_at": expired}})

    me = await client.get("/auth/me")
    assert me.status_code == 401


#--- rename ---

async def test_rename_display_name(client):
    await client.post("/auth/register", json=ALICE)

    response = await client.put("/auth/me", json={"display_name": "Alicia"})

    assert response.status_code == 200
    me = await client.get("/auth/me")
    assert me.json()["display_name"] == "Alicia"


async def test_rename_collision_409(client):
    await client.post("/auth/register", json=ALICE)
    await client.post("/auth/logout")
    await client.post("/auth/register", json=BOB)

    response = await client.put("/auth/me", json={"display_name": "ALICE"})

    assert response.status_code == 409


async def test_rename_requires_auth(client):
    response = await client.put("/auth/me", json={"display_name": "Nobody"})

    assert response.status_code == 401
