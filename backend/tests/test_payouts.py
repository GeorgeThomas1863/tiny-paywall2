from db.connection import get_db
from tests.helpers import (
    assert_ledger_matches_balances,
    create_published_article,
    fund_wallet,
    register_user,
)

ALICE = ("alice@test.com", "Alice")
BOB = ("bob@test.com", "Bob")
ADMIN = ("admin@test.com", "Admin")
DESTINATION = "PayPal: alice@example.com"

# Each sale of a 500¢ article credits the author 400¢ (80% split).
SALE_PRICE_CENTS = 500
AUTHOR_CUT_CENTS = 400


#--- helpers ---

async def setup_author_with_earnings(make_client, sales=3):
    """Alice sells `sales` articles at 500¢ to Bob → earnings = sales * 400¢."""
    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)
    await sell_articles(alice_client, bob_client, bob, sales, "cs_payout_fund")
    return alice_client, bob_client, alice, bob


async def sell_articles(alice_client, bob_client, bob, count, fund_tag):
    await fund_wallet(bob["_id"], count * SALE_PRICE_CENTS, fund_tag)
    for _ in range(count):
        article_id = await create_published_article(
            alice_client, price_cents=SALE_PRICE_CENTS
        )
        response = await bob_client.post("/purchases", json={"article_id": article_id})
        assert response.status_code == 200


async def make_admin_client(make_client):
    admin_client = await make_client()
    await register_user(admin_client, *ADMIN)
    await get_db().users.update_one(
        {"email": ADMIN[0]}, {"$set": {"is_admin": True}}
    )
    return admin_client


async def request_payout(client, destination=DESTINATION):
    response = await client.post("/payouts/request", json={"destination": destination})
    assert response.status_code == 200
    return response.json()


async def get_earnings(client):
    return (await client.get("/auth/me")).json()["earnings_cents"]


async def find_only_request():
    requests = await get_db().payout_requests.find({}).to_list(None)
    assert len(requests) == 1
    return requests[0]


#--- request ---

async def test_payout_routes_require_auth(client):
    request = await client.post("/payouts/request", json={"destination": DESTINATION})
    mine = await client.get("/payouts/mine")

    assert request.status_code == 401
    assert mine.status_code == 401


async def test_request_reserves_full_earnings(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)

    result = await request_payout(alice_client)

    assert result["success"] is True
    assert await get_earnings(alice_client) == 0

    request = await find_only_request()
    assert request["user_id"] == alice["_id"]
    assert request["amount_cents"] == 1200
    assert request["destination"] == DESTINATION
    assert request["status"] == "requested"
    assert request["resolved_at"] is None

    reserve = await get_db().ledger.find_one({"type": "payout_reserve"})
    assert reserve["user_id"] == alice["_id"]
    assert reserve["balance"] == "earnings"
    assert reserve["amount_cents"] == -1200
    assert reserve["payout_request_id"] == request["_id"]

    await assert_ledger_matches_balances()


async def test_request_below_threshold_422(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client, sales=2)

    response = await alice_client.post(
        "/payouts/request", json={"destination": DESTINATION}
    )

    assert response.status_code == 422
    assert await get_earnings(alice_client) == 800
    assert await get_db().payout_requests.count_documents({}) == 0


async def test_second_request_while_pending_409(make_client):
    alice_client, bob_client, alice, bob = await setup_author_with_earnings(make_client)
    await request_payout(alice_client)
    await sell_articles(alice_client, bob_client, bob, 3, "cs_payout_refund")
    assert await get_earnings(alice_client) == 1200

    response = await alice_client.post(
        "/payouts/request", json={"destination": DESTINATION}
    )

    assert response.status_code == 409
    assert await get_earnings(alice_client) == 1200
    assert await get_db().payout_requests.count_documents({}) == 1


async def test_request_destination_validation_422(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)

    empty = await alice_client.post("/payouts/request", json={"destination": "   "})
    too_long = await alice_client.post(
        "/payouts/request", json={"destination": "x" * 201}
    )

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert await get_earnings(alice_client) == 1200
    assert await get_db().payout_requests.count_documents({}) == 0


#--- mine ---

async def test_mine_lists_own_requests_newest_first(make_client):
    alice_client, bob_client, alice, bob = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)

    await request_payout(alice_client, destination="first destination")
    first_id = str((await find_only_request())["_id"])
    reject = await admin_client.put(f"/payouts/{first_id}", json={"status": "rejected"})
    assert reject.status_code == 200
    await request_payout(alice_client, destination="second destination")

    items = (await alice_client.get("/payouts/mine")).json()

    assert len(items) == 2
    assert items[0]["destination"] == "second destination"
    assert items[0]["status"] == "requested"
    assert items[0]["amount_cents"] == 1200
    assert items[0]["resolved_at"] is None
    assert items[1]["destination"] == "first destination"
    assert items[1]["status"] == "rejected"
    assert items[1]["resolved_at"] is not None


#--- admin resolve ---

async def test_admin_reject_returns_funds(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)
    await request_payout(alice_client)
    request_id = str((await find_only_request())["_id"])

    response = await admin_client.put(
        f"/payouts/{request_id}", json={"status": "rejected"}
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert await get_earnings(alice_client) == 1200

    request = await find_only_request()
    assert request["status"] == "rejected"
    assert request["resolved_at"] is not None

    returned = await get_db().ledger.find_one({"type": "payout_return"})
    assert returned["user_id"] == alice["_id"]
    assert returned["balance"] == "earnings"
    assert returned["amount_cents"] == 1200
    assert returned["payout_request_id"] == request["_id"]

    await assert_ledger_matches_balances()


async def test_admin_paid_flips_status_only(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)
    await request_payout(alice_client)
    request_id = str((await find_only_request())["_id"])
    ledger_count_before = await get_db().ledger.count_documents({})

    response = await admin_client.put(f"/payouts/{request_id}", json={"status": "paid"})

    assert response.status_code == 200
    assert await get_earnings(alice_client) == 0

    request = await find_only_request()
    assert request["status"] == "paid"
    assert request["resolved_at"] is not None

    assert await get_db().ledger.count_documents({}) == ledger_count_before
    await assert_ledger_matches_balances()


async def test_resolving_already_resolved_409(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)
    await request_payout(alice_client)
    request_id = str((await find_only_request())["_id"])
    paid = await admin_client.put(f"/payouts/{request_id}", json={"status": "paid"})
    assert paid.status_code == 200

    response = await admin_client.put(
        f"/payouts/{request_id}", json={"status": "rejected"}
    )

    assert response.status_code == 409
    assert await get_earnings(alice_client) == 0
    assert (await find_only_request())["status"] == "paid"


async def test_resolve_invalid_status_422(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)
    await request_payout(alice_client)
    request_id = str((await find_only_request())["_id"])

    response = await admin_client.put(f"/payouts/{request_id}", json={"status": "bogus"})

    assert response.status_code == 422


async def test_resolve_missing_request_404(make_client):
    admin_client = await make_admin_client(make_client)

    malformed = await admin_client.put("/payouts/not-an-id", json={"status": "paid"})
    missing = await admin_client.put(
        "/payouts/000000000000000000000000", json={"status": "paid"}
    )

    assert malformed.status_code == 404
    assert missing.status_code == 404


#--- admin list ---

async def test_admin_list_includes_requester_and_filters(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    admin_client = await make_admin_client(make_client)

    await request_payout(alice_client, destination="first destination")
    first_id = str((await find_only_request())["_id"])
    await admin_client.put(f"/payouts/{first_id}", json={"status": "rejected"})
    await request_payout(alice_client, destination="second destination")

    everything = (await admin_client.get("/payouts")).json()
    pending_only = (await admin_client.get("/payouts?status=requested")).json()

    assert len(everything) == 2
    assert everything[0]["email"] == "alice@test.com"
    assert everything[0]["display_name"] == "Alice"
    assert everything[0]["destination"] == "second destination"

    assert len(pending_only) == 1
    assert pending_only[0]["status"] == "requested"


async def test_non_admin_on_admin_routes_403(make_client):
    alice_client, _, alice, _ = await setup_author_with_earnings(make_client)
    await request_payout(alice_client)
    request_id = str((await find_only_request())["_id"])

    listing = await alice_client.get("/payouts")
    resolve = await alice_client.put(f"/payouts/{request_id}", json={"status": "paid"})

    assert listing.status_code == 403
    assert resolve.status_code == 403
    assert (await find_only_request())["status"] == "requested"
