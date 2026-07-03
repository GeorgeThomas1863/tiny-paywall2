from types import SimpleNamespace

from db.connection import get_db
from tests.helpers import fund_wallet, register_user

ALICE = ("alice@test.com", "Alice")


async def test_topup_requires_auth(client):
    response = await client.post("/wallet/topup", json={"amount_cents": 500})

    assert response.status_code == 401


async def test_topup_rejects_non_preset_amounts(client):
    await register_user(client, *ALICE)

    for bad_amount in (0, 300, 999, 2500, -500):
        response = await client.post("/wallet/topup", json={"amount_cents": bad_amount})
        assert response.status_code == 422, f"expected 422 for {bad_amount}"


async def test_topup_creates_checkout_session(client, monkeypatch):
    alice = await register_user(client, *ALICE)

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    monkeypatch.setattr("stripe.checkout.Session.create", fake_create)

    response = await client.post("/wallet/topup", json={"amount_cents": 1000})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["url"] == "https://checkout.stripe.test/session"

    assert captured["mode"] == "payment"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 1000
    assert captured["line_items"][0]["price_data"]["currency"] == "usd"
    assert captured["metadata"] == {"user_id": str(alice["_id"]), "amount_cents": "1000"}
    assert captured["success_url"].endswith(
        "/account?topup=success&session_id={CHECKOUT_SESSION_ID}"
    )
    assert captured["cancel_url"].endswith("/account")


async def test_history_requires_auth(client):
    response = await client.get("/wallet/history")

    assert response.status_code == 401


async def test_history_returns_entries_newest_first(client):
    alice = await register_user(client, *ALICE)
    await fund_wallet(alice["_id"], 500, "cs_history_1")
    await fund_wallet(alice["_id"], 1000, "cs_history_2")

    response = await client.get("/wallet/history")

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
    assert [entry["amount_cents"] for entry in entries] == [1000, 500]
    assert [entry["stripe_session_id"] for entry in entries] == ["cs_history_2", "cs_history_1"]
    for entry in entries:
        assert entry["type"] == "topup"
        assert entry["balance"] == "wallet"
        assert "created_at" in entry


async def test_history_only_shows_own_entries(client, make_client):
    alice = await register_user(client, *ALICE)
    bob_client = await make_client()
    bob = await register_user(bob_client, "bob@test.com", "Bob")

    await fund_wallet(alice["_id"], 500, "cs_own_1")
    await fund_wallet(bob["_id"], 1000, "cs_own_2")

    entries = (await client.get("/wallet/history")).json()

    assert len(entries) == 1
    assert entries[0]["amount_cents"] == 500
