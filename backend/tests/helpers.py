from db.connection import get_db

ARTICLE_FIELDS = {
    "title": "Paid Article",
    "summary": "A public teaser",
    "body": "The secret paid body",
    "price_cents": 25,
}


async def register_user(client, email, display_name, password="password123"):
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert response.status_code == 200
    return await get_db().users.find_one({"email": email})


async def create_published_article(client, **overrides):
    response = await client.post("/articles", json={**ARTICLE_FIELDS, **overrides})
    assert response.status_code == 200
    article_id = response.json()["id"]

    publish = await client.put(f"/articles/{article_id}", json={"status": "published"})
    assert publish.status_code == 200
    return article_id


async def fund_wallet(user_id, amount_cents, stripe_session_id):
    from money.operations import credit_topup

    result = await credit_topup(user_id, amount_cents, stripe_session_id)
    assert result["success"] is True


async def assert_ledger_matches_balances():
    db = get_db()
    async for user in db.users.find({}):
        for balance, field in (("wallet", "wallet_cents"), ("earnings", "earnings_cents")):
            entries = await db.ledger.find(
                {"user_id": user["_id"], "balance": balance}
            ).to_list(None)
            total = 0
            for entry in entries:
                total += entry["amount_cents"]
            assert total == user[field], (
                f"{user['email']} {balance}: ledger sum {total} != stored {user[field]}"
            )
