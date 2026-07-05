from tests.helpers import create_published_article, fund_wallet, register_user

ALICE = ("alice@test.com", "Alice")
BOB = ("bob@test.com", "Bob")
CARA = ("cara@test.com", "Cara")


#--- helpers ---

async def setup_purchased_article(make_client):
    alice_client = await make_client()
    bob_client = await make_client()
    await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)
    article_id = await create_published_article(alice_client)
    await fund_wallet(bob["_id"], 500, "cs_vote_fund_bob")

    purchase = await bob_client.post("/purchases", json={"article_id": article_id})
    assert purchase.status_code == 200
    return alice_client, bob_client, article_id


async def cast_vote(client, article_id, value):
    return await client.put(f"/articles/{article_id}/vote", json={"value": value})


#--- tests ---

async def test_vote_requires_auth(client):
    response = await client.put(
        "/articles/000000000000000000000000/vote", json={"value": 1}
    )

    assert response.status_code == 401


async def test_non_purchaser_cannot_vote(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)
    cara_client = await make_client()
    await register_user(cara_client, *CARA)

    response = await cast_vote(cara_client, article_id, 1)

    assert response.status_code == 403


async def test_author_cannot_vote_on_own_article(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    response = await cast_vote(alice_client, article_id, 1)

    assert response.status_code == 403


async def test_purchaser_upvote_counts(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    response = await cast_vote(bob_client, article_id, 1)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["score"] == 1
    assert body["my_vote"] == 1

    detail = (await bob_client.get(f"/articles/{article_id}")).json()
    assert detail["score"] == 1
    assert detail["my_vote"] == 1


async def test_switching_vote_flips_score(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    await cast_vote(bob_client, article_id, 1)
    response = await cast_vote(bob_client, article_id, -1)

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == -1
    assert body["my_vote"] == -1


async def test_clearing_vote_resets_score(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    await cast_vote(bob_client, article_id, 1)
    response = await cast_vote(bob_client, article_id, 0)

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0
    assert body["my_vote"] == 0


async def test_invalid_vote_value_422(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    response = await cast_vote(bob_client, article_id, 5)

    assert response.status_code == 422


async def test_vote_on_missing_article_404(make_client):
    alice_client, bob_client, _ = await setup_purchased_article(make_client)

    response = await cast_vote(bob_client, "000000000000000000000000", 1)

    assert response.status_code == 404


async def test_opposite_votes_cancel_out(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)
    cara_client = await make_client()
    cara = await register_user(cara_client, *CARA)
    await fund_wallet(cara["_id"], 500, "cs_vote_fund_cara")
    purchase = await cara_client.post("/purchases", json={"article_id": article_id})
    assert purchase.status_code == 200

    await cast_vote(bob_client, article_id, 1)
    response = await cast_vote(cara_client, article_id, -1)

    assert response.json()["score"] == 0

    detail = (await bob_client.get(f"/articles/{article_id}")).json()
    assert detail["score"] == 0
    assert detail["my_vote"] == 1


async def test_listing_includes_score(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)
    await cast_vote(bob_client, article_id, 1)

    listing = (await bob_client.get("/articles")).json()

    assert listing[0]["score"] == 1


async def test_non_purchaser_sees_score_and_null_my_vote(make_client, client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)
    await cast_vote(bob_client, article_id, 1)

    detail = (await client.get(f"/articles/{article_id}")).json()

    assert detail["score"] == 1
    assert detail["my_vote"] is None


async def test_unvoted_article_scores_zero(make_client):
    alice_client, bob_client, article_id = await setup_purchased_article(make_client)

    detail = (await bob_client.get(f"/articles/{article_id}")).json()
    listing = (await bob_client.get("/articles")).json()

    assert detail["score"] == 0
    assert detail["my_vote"] == 0
    assert listing[0]["score"] == 0
