import pytest
from bson import ObjectId
from fastapi import HTTPException

from db.connection import get_db
from tests.helpers import fund_wallet

ALICE = {"email": "alice@test.com", "password": "password123", "display_name": "Alice"}
BOB = {"email": "bob@test.com", "password": "password456", "display_name": "Bob"}
ADMIN = {"email": "admin@test.com", "password": "password789", "display_name": "Admin"}

ARTICLE = {
    "title": "Test Article",
    "summary": "A public teaser",
    "body": "The secret full body text",
    "price_cents": 25,
}


#--- helpers ---

async def register(client, creds):
    response = await client.post("/auth/register", json=creds)
    assert response.status_code == 200


async def make_admin(email):
    await get_db().users.update_one({"email": email}, {"$set": {"is_admin": True}})


async def create_article(client, **overrides):
    response = await client.post("/articles", json={**ARTICLE, **overrides})
    assert response.status_code == 200
    return response.json()["id"]


async def create_published_article(client, **overrides):
    article_id = await create_article(client, **overrides)
    response = await client.put(f"/articles/{article_id}", json={"status": "published"})
    assert response.status_code == 200
    return article_id


#--- create ---

async def test_create_requires_auth(client):
    response = await client.post("/articles", json=ARTICLE)

    assert response.status_code == 401


async def test_create_starts_as_draft(client):
    await register(client, ALICE)

    article_id = await create_article(client)

    article = await get_db().articles.find_one({})
    assert str(article["_id"]) == article_id
    assert article["status"] == "draft"
    assert article["price_cents"] == 25


async def test_create_validation_bounds(client):
    await register(client, ALICE)

    bad_payloads = [
        {**ARTICLE, "title": "   "},
        {**ARTICLE, "title": "x" * 201},
        {**ARTICLE, "summary": ""},
        {**ARTICLE, "summary": "x" * 1001},
        {**ARTICLE, "body": "   "},
        {**ARTICLE, "price_cents": 0},
        {**ARTICLE, "price_cents": 501},
    ]
    for payload in bad_payloads:
        response = await client.post("/articles", json=payload)
        assert response.status_code == 422, f"expected 422 for {payload}"


#--- public list ---

async def test_list_shows_published_only_without_body(client, make_client):
    alice = await make_client()
    await register(alice, ALICE)
    await create_article(alice, title="Draft one")
    await create_published_article(alice, title="Published one")

    response = await client.get("/articles")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Published one"
    assert item["summary"] == ARTICLE["summary"]
    assert item["price_cents"] == 25
    assert item["author_name"] == "Alice"
    assert item["owned"] is False
    assert "body" not in item
    assert "created_at" in item


async def test_list_newest_first(client, make_client):
    alice = await make_client()
    await register(alice, ALICE)
    await create_published_article(alice, title="Older")
    await create_published_article(alice, title="Newer")

    items = (await client.get("/articles")).json()

    assert [item["title"] for item in items] == ["Newer", "Older"]


async def test_list_marks_own_articles_owned(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    await create_published_article(alice)

    items = (await alice.get("/articles")).json()

    assert items[0]["owned"] is True


#--- public detail ---

async def test_detail_teaser_never_leaks_body(client, make_client):
    alice = await make_client()
    await register(alice, ALICE)
    article_id = await create_published_article(alice)

    response = await client.get(f"/articles/{article_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == ARTICLE["title"]
    assert data["owned"] is False
    assert "body" not in data
    assert "status" not in data


async def test_detail_no_body_for_logged_in_non_owner(make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    article_id = await create_published_article(alice)

    data = (await bob.get(f"/articles/{article_id}")).json()

    assert data["owned"] is False
    assert "body" not in data


async def test_author_reads_own_article_with_body(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    article_id = await create_published_article(alice)

    data = (await alice.get(f"/articles/{article_id}")).json()

    assert data["owned"] is True
    assert data["body"] == ARTICLE["body"]
    assert data["status"] == "published"


async def test_admin_reads_any_article_with_body(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    article_id = await create_published_article(alice)

    data = (await admin.get(f"/articles/{article_id}")).json()

    assert data["owned"] is True
    assert data["body"] == ARTICLE["body"]


async def test_draft_hidden_from_everyone_but_author_and_admin(client, make_client):
    alice = await make_client()
    bob = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    article_id = await create_article(alice)

    assert (await client.get(f"/articles/{article_id}")).status_code == 404
    assert (await bob.get(f"/articles/{article_id}")).status_code == 404

    author_view = await alice.get(f"/articles/{article_id}")
    assert author_view.status_code == 200
    assert author_view.json()["status"] == "draft"

    admin_view = await admin.get(f"/articles/{article_id}")
    assert admin_view.status_code == 200


async def test_malformed_id_404(client):
    response = await client.get("/articles/not-a-real-id")

    assert response.status_code == 404


#--- update ---

async def test_author_updates_own_article(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    article_id = await create_article(alice)

    response = await alice.put(
        f"/articles/{article_id}",
        json={"title": "New Title", "price_cents": 99, "status": "published"},
    )

    assert response.status_code == 200
    article = await get_db().articles.find_one({})
    assert article["title"] == "New Title"
    assert article["price_cents"] == 99
    assert article["status"] == "published"
    assert article["updated_at"] > article["created_at"]


async def test_update_rejected_for_non_author(make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    article_id = await create_published_article(alice)

    response = await bob.put(f"/articles/{article_id}", json={"title": "Hijacked"})

    assert response.status_code == 403


async def test_admin_updates_any_article(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    article_id = await create_published_article(alice)

    response = await admin.put(f"/articles/{article_id}", json={"status": "draft"})

    assert response.status_code == 200
    article = await get_db().articles.find_one({})
    assert article["status"] == "draft"


async def test_update_validation(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    article_id = await create_article(alice)

    bad_payloads = [
        {"price_cents": 0},
        {"price_cents": 501},
        {"title": "   "},
        {"status": "archived"},
        {},
    ]
    for payload in bad_payloads:
        response = await alice.put(f"/articles/{article_id}", json=payload)
        assert response.status_code == 422, f"expected 422 for {payload}"


#--- delete ---

async def test_author_deletes_own_article(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    article_id = await create_published_article(alice)

    response = await alice.delete(f"/articles/{article_id}")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert await get_db().articles.find_one({}) is None


async def test_delete_rejected_for_non_author(make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    article_id = await create_published_article(alice)

    response = await bob.delete(f"/articles/{article_id}")

    assert response.status_code == 403
    assert await get_db().articles.find_one({}) is not None


async def test_admin_deletes_any_article(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    article_id = await create_published_article(alice)

    response = await admin.delete(f"/articles/{article_id}")

    assert response.status_code == 200
    assert await get_db().articles.find_one({}) is None


#--- mine ---

async def test_mine_requires_auth(client):
    response = await client.get("/articles/mine")

    assert response.status_code == 401


async def test_mine_returns_all_statuses_with_zero_stats(make_client):
    alice = await make_client()
    await register(alice, ALICE)
    await create_article(alice, title="My draft")
    await create_published_article(alice, title="My published")

    response = await alice.get("/articles/mine")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    for item in items:
        assert item["sales_count"] == 0
        assert item["earned_cents"] == 0
        assert item["status"] in ("draft", "published")
    assert {item["title"] for item in items} == {"My draft", "My published"}


async def test_mine_excludes_other_authors(make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    await create_published_article(alice)

    items = (await bob.get("/articles/mine")).json()

    assert items == []


#--- purchased flag ---

async def fund_and_buy(client, email, article_id, stripe_tag):
    buyer = await get_db().users.find_one({"email": email})
    await fund_wallet(buyer["_id"], 100, stripe_tag)
    response = await client.post("/purchases", json={"article_id": article_id})
    assert response.status_code == 200


async def test_list_purchased_flag_tracks_actual_purchases(make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    bought_id = await create_published_article(alice, title="Bought")
    await create_published_article(alice, title="Not bought")
    await fund_and_buy(bob, BOB["email"], bought_id, "cs_purchased_list")

    items = {item["title"]: item for item in (await bob.get("/articles")).json()}

    assert items["Bought"]["purchased"] is True
    assert items["Bought"]["owned"] is True
    assert items["Not bought"]["purchased"] is False
    assert items["Not bought"]["owned"] is False


async def test_author_and_admin_own_without_purchased(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    await create_published_article(alice)

    author_item = (await alice.get("/articles")).json()[0]
    admin_item = (await admin.get("/articles")).json()[0]

    assert author_item["owned"] is True
    assert author_item["purchased"] is False
    assert admin_item["owned"] is True
    assert admin_item["purchased"] is False


async def test_detail_includes_purchased(client, make_client):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    article_id = await create_published_article(alice)
    await fund_and_buy(bob, BOB["email"], article_id, "cs_purchased_detail")

    assert (await bob.get(f"/articles/{article_id}")).json()["purchased"] is True
    assert (await alice.get(f"/articles/{article_id}")).json()["purchased"] is False
    assert (await client.get(f"/articles/{article_id}")).json()["purchased"] is False


#--- admin list ---

async def test_admin_list_has_no_entitlement_or_score_fields(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    await create_published_article(alice)

    item = (await admin.get("/articles/all")).json()[0]

    for field in ("score", "owned", "purchased"):
        assert field not in item, f"admin list should not carry {field}"


async def test_admin_list_shows_everything(make_client):
    alice = await make_client()
    admin = await make_client()
    await register(alice, ALICE)
    await register(admin, ADMIN)
    await make_admin(ADMIN["email"])
    await create_article(alice, title="Draft")
    await create_published_article(alice, title="Published")

    response = await admin.get("/articles/all")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    for item in items:
        assert item["author_name"] == "Alice"
        assert "status" in item
        assert "body" not in item


async def test_admin_list_forbidden_for_non_admin(make_client):
    alice = await make_client()
    await register(alice, ALICE)

    response = await alice.get("/articles/all")

    assert response.status_code == 403


#--- failure modes ---

class _FailingCollection:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise RuntimeError("simulated mongo failure")

        return fail


class _FailingPurchasesDB:
    def __init__(self, real_db):
        self._real_db = real_db

    def __getattr__(self, name):
        if name == "purchases":
            return _FailingCollection()
        return getattr(self._real_db, name)


async def test_purchases_lookup_failure_is_500_not_teaser(make_client, monkeypatch):
    alice = await make_client()
    bob = await make_client()
    await register(alice, ALICE)
    await register(bob, BOB)
    article_id = await create_published_article(alice)

    monkeypatch.setattr("routes.articles.get_db", lambda: _FailingPurchasesDB(get_db()))

    response = await bob.get(f"/articles/{article_id}")
    assert response.status_code == 500


async def test_sales_stats_failure_is_500_not_zeros(make_client, monkeypatch):
    alice = await make_client()
    await register(alice, ALICE)
    await create_published_article(alice)

    monkeypatch.setattr("routes.articles.get_db", lambda: _FailingPurchasesDB(get_db()))

    response = await alice.get("/articles/mine")
    assert response.status_code == 500


async def test_update_vanished_article_404():
    from routes.articles import apply_article_update

    with pytest.raises(HTTPException) as excinfo:
        await apply_article_update(ObjectId(), {"title": "ghost"})
    assert excinfo.value.status_code == 404


async def test_delete_vanished_article_404():
    from routes.articles import remove_article

    with pytest.raises(HTTPException) as excinfo:
        await remove_article(ObjectId())
    assert excinfo.value.status_code == 404
