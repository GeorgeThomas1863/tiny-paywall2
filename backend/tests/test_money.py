from db.connection import get_db
from tests.helpers import (
    assert_ledger_matches_balances,
    create_published_article,
    fund_wallet,
    register_user,
)

ALICE = ("alice@test.com", "Alice")
BOB = ("bob@test.com", "Bob")


async def test_split_rounding_table():
    from money.operations import split_sale

    table = [
        (1, 1, 0),
        (2, 2, 0),
        (3, 2, 1),
        (25, 20, 5),
        (42, 34, 8),
        (100, 80, 20),
        (500, 400, 100),
    ]
    for price_cents, expected_author, expected_platform in table:
        author_cents, platform_cents = split_sale(price_cents)
        assert (author_cents, platform_cents) == (expected_author, expected_platform)
        assert author_cents + platform_cents == price_cents


async def test_topup_credits_wallet_and_writes_ledger(make_client):
    alice_client = await make_client()
    alice = await register_user(alice_client, *ALICE)

    await fund_wallet(alice["_id"], 500, "cs_test_topup_1")

    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 500

    entry = await get_db().ledger.find_one({"user_id": alice["_id"]})
    assert entry["type"] == "topup"
    assert entry["balance"] == "wallet"
    assert entry["amount_cents"] == 500
    assert entry["stripe_session_id"] == "cs_test_topup_1"


async def test_topup_replay_credits_exactly_once(make_client):
    alice_client = await make_client()
    alice = await register_user(alice_client, *ALICE)

    from money.operations import credit_topup

    first = await credit_topup(alice["_id"], 500, "cs_test_replay")
    second = await credit_topup(alice["_id"], 500, "cs_test_replay")

    assert first["success"] is True
    assert second["success"] is True

    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 500
    assert await get_db().ledger.count_documents({"user_id": alice["_id"]}) == 1


async def test_purchase_moves_money_atomically(make_client):
    from money.operations import execute_purchase

    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)

    article_id = await create_published_article(alice_client, price_cents=25)
    article = await get_db().articles.find_one({})
    await fund_wallet(bob["_id"], 500, "cs_test_fund_bob")

    result = await execute_purchase(bob, article)

    assert result["success"] is True
    buyer = await get_db().users.find_one({"_id": bob["_id"]})
    author = await get_db().users.find_one({"_id": alice["_id"]})
    assert buyer["wallet_cents"] == 475
    assert author["earnings_cents"] == 20

    purchase = await get_db().purchases.find_one({})
    assert purchase["buyer_id"] == bob["_id"]
    assert str(purchase["article_id"]) == article_id
    assert purchase["price_cents"] == 25
    assert purchase["author_cents"] == 20
    assert purchase["platform_cents"] == 5

    buyer_entry = await get_db().ledger.find_one({"user_id": bob["_id"], "type": "purchase"})
    author_entry = await get_db().ledger.find_one({"user_id": alice["_id"], "type": "sale"})
    assert buyer_entry["amount_cents"] == -25
    assert buyer_entry["purchase_id"] == purchase["_id"]
    assert author_entry["amount_cents"] == 20
    assert author_entry["purchase_id"] == purchase["_id"]

    await assert_ledger_matches_balances()


async def test_insufficient_funds_changes_nothing(make_client):
    from money.operations import execute_purchase

    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)

    await create_published_article(alice_client, price_cents=25)
    article = await get_db().articles.find_one({})
    await fund_wallet(bob["_id"], 10, "cs_test_tiny_fund")

    result = await execute_purchase(bob, article)

    assert result["success"] is False
    assert result["status_code"] == 402

    buyer = await get_db().users.find_one({"_id": bob["_id"]})
    author = await get_db().users.find_one({"_id": alice["_id"]})
    assert buyer["wallet_cents"] == 10
    assert author["earnings_cents"] == 0
    assert await get_db().purchases.count_documents({}) == 0
    await assert_ledger_matches_balances()


async def test_penny_article_pays_author_full_cent(make_client):
    from money.operations import execute_purchase

    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)

    await create_published_article(alice_client, price_cents=1)
    article = await get_db().articles.find_one({})
    await fund_wallet(bob["_id"], 500, "cs_test_penny")

    result = await execute_purchase(bob, article)

    assert result["success"] is True
    author = await get_db().users.find_one({"_id": alice["_id"]})
    assert author["earnings_cents"] == 1

    purchase = await get_db().purchases.find_one({})
    assert purchase["author_cents"] == 1
    assert purchase["platform_cents"] == 0
    await assert_ledger_matches_balances()


async def test_topup_to_missing_user_fails_without_ledger_row(make_client):
    from bson import ObjectId

    from money.operations import credit_topup

    result = await credit_topup(ObjectId(), 500, "cs_ghost")

    assert result["success"] is False
    assert result["status_code"] == 500
    assert await get_db().ledger.count_documents({}) == 0


async def test_purchase_with_missing_author_aborts_fully(make_client):
    from money.operations import execute_purchase

    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)

    await create_published_article(alice_client, price_cents=25)
    article = await get_db().articles.find_one({})
    await fund_wallet(bob["_id"], 500, "cs_orphan_fund")
    await get_db().users.delete_one({"_id": alice["_id"]})

    result = await execute_purchase(bob, article)

    assert result["success"] is False
    assert result["status_code"] == 500

    buyer = await get_db().users.find_one({"_id": bob["_id"]})
    assert buyer["wallet_cents"] == 500
    assert await get_db().purchases.count_documents({}) == 0
    assert await get_db().ledger.count_documents({}) == 1  # only bob's top-up
    await assert_ledger_matches_balances()


async def test_ledger_invariant_after_operation_sequence(make_client):
    from money.operations import execute_purchase

    alice_client = await make_client()
    bob_client = await make_client()
    alice = await register_user(alice_client, *ALICE)
    bob = await register_user(bob_client, *BOB)

    await create_published_article(alice_client, title="First", price_cents=42)
    await create_published_article(alice_client, title="Second", price_cents=199)
    articles = await get_db().articles.find({}).to_list(None)

    await fund_wallet(bob["_id"], 500, "cs_seq_1")
    await fund_wallet(bob["_id"], 1000, "cs_seq_2")
    for article in articles:
        result = await execute_purchase(bob, article)
        assert result["success"] is True

    await assert_ledger_matches_balances()
