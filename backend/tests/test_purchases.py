from db.connection import get_db
from tests.helpers import create_published_article, fund_wallet, register_user

ALICE = ("alice@test.com", "Alice")
BOB = ("bob@test.com", "Bob")


#--- helpers ---

async def setup_marketplace(make_client, price_cents=25, bob_funds=500):
    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)
    article_id = await create_published_article(alice_client, price_cents=price_cents)
    if bob_funds:
        await fund_wallet(bob["_id"], bob_funds, "cs_purchase_fund")
    return alice_client, bob_client, alice, bob, article_id


#--- tests ---

async def test_purchase_requires_auth(client):
    response = await client.post("/purchases", json={"article_id": "irrelevant"})

    assert response.status_code == 401


async def test_purchase_unlocks_article(make_client):
    alice_client, bob_client, alice, bob, article_id = await setup_marketplace(make_client)

    response = await bob_client.post("/purchases", json={"article_id": article_id})

    assert response.status_code == 200
    assert response.json()["success"] is True

    me = (await bob_client.get("/auth/me")).json()
    assert me["wallet_cents"] == 475

    author_me = (await alice_client.get("/auth/me")).json()
    assert author_me["earnings_cents"] == 20

    detail = (await bob_client.get(f"/articles/{article_id}")).json()
    assert detail["owned"] is True
    assert detail["body"] == "The secret paid body"

    listing = (await bob_client.get("/articles")).json()
    assert listing[0]["owned"] is True


async def test_insufficient_funds_402(make_client):
    _, bob_client, alice, bob, article_id = await setup_marketplace(make_client, bob_funds=10)

    response = await bob_client.post("/purchases", json={"article_id": article_id})

    assert response.status_code == 402
    me = (await bob_client.get("/auth/me")).json()
    assert me["wallet_cents"] == 10
    assert await get_db().purchases.count_documents({}) == 0


async def test_repeat_purchase_409_charged_once(make_client):
    _, bob_client, alice, bob, article_id = await setup_marketplace(make_client)

    first = await bob_client.post("/purchases", json={"article_id": article_id})
    second = await bob_client.post("/purchases", json={"article_id": article_id})

    assert first.status_code == 200
    assert second.status_code == 409

    me = (await bob_client.get("/auth/me")).json()
    assert me["wallet_cents"] == 475
    assert await get_db().purchases.count_documents({}) == 1


async def test_buying_own_article_rejected(make_client):
    alice_client, _, alice, bob, article_id = await setup_marketplace(make_client)
    await fund_wallet(alice["_id"], 500, "cs_self_fund")

    response = await alice_client.post("/purchases", json={"article_id": article_id})

    assert response.status_code == 409
    me = (await alice_client.get("/auth/me")).json()
    assert me["wallet_cents"] == 500
    assert me["earnings_cents"] == 0


async def test_draft_not_purchasable(make_client):
    alice_client = await make_client()
    bob_client = await make_client()
    await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)
    await fund_wallet(bob["_id"], 500, "cs_draft_fund")

    create = await alice_client.post("/articles", json={
        "title": "Draft", "summary": "teaser", "body": "body", "price_cents": 25,
    })
    draft_id = create.json()["id"]

    response = await bob_client.post("/purchases", json={"article_id": draft_id})

    assert response.status_code == 404


async def test_missing_article_404(make_client):
    _, bob_client, alice, bob, _ = await setup_marketplace(make_client)

    response = await bob_client.post(
        "/purchases", json={"article_id": "000000000000000000000000"}
    )

    assert response.status_code == 404


async def test_buyer_keeps_access_after_price_and_content_change(make_client):
    alice_client, bob_client, alice, bob, article_id = await setup_marketplace(make_client)

    await bob_client.post("/purchases", json={"article_id": article_id})
    update = await alice_client.put(
        f"/articles/{article_id}", json={"price_cents": 499, "body": "Updated body text"}
    )
    assert update.status_code == 200

    detail = (await bob_client.get(f"/articles/{article_id}")).json()
    assert detail["owned"] is True
    assert detail["body"] == "Updated body text"
