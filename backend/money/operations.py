from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from db.connection import get_db, get_db_client

AUTHOR_SHARE_PERCENT = 80


class InsufficientFunds(Exception):
    pass


#--- operations (the ONLY functions that change balances — SPEC §2.4) ---

async def credit_topup(user_id, amount_cents, stripe_session_id):
    async def apply_topup(session):
        db = get_db()
        entry = build_ledger_entry(user_id, "wallet", amount_cents, "topup")
        entry["stripe_session_id"] = stripe_session_id
        await db.ledger.insert_one(entry, session=session)
        await db.users.update_one(
            {"_id": user_id}, {"$inc": {"wallet_cents": amount_cents}}, session=session
        )

    try:
        await run_transaction(apply_topup)
        return {"success": True, "message": "Wallet credited"}
    except DuplicateKeyError:
        # Webhook replay: the ledger's unique stripe_session_id index already recorded it.
        return {"success": True, "message": "Top-up already credited"}
    except Exception as e:
        print(f"MONEY ERROR CREDITING TOPUP {stripe_session_id} for {user_id}: {e}")
        return {"success": False, "message": "Failed to credit wallet", "status_code": 500}


async def execute_purchase(buyer, article):
    price_cents = article["price_cents"]
    author_cents, platform_cents = split_sale(price_cents)

    async def apply_purchase(session):
        db = get_db()
        debited = await db.users.find_one_and_update(
            {"_id": buyer["_id"], "wallet_cents": {"$gte": price_cents}},
            {"$inc": {"wallet_cents": -price_cents}},
            session=session,
        )
        if debited is None:
            raise InsufficientFunds()

        purchase_doc = build_purchase_doc(buyer["_id"], article, author_cents, platform_cents)
        inserted = await db.purchases.insert_one(purchase_doc, session=session)

        await db.users.update_one(
            {"_id": article["author_id"]},
            {"$inc": {"earnings_cents": author_cents}},
            session=session,
        )

        buyer_entry = build_ledger_entry(buyer["_id"], "wallet", -price_cents, "purchase")
        buyer_entry["purchase_id"] = inserted.inserted_id
        author_entry = build_ledger_entry(
            article["author_id"], "earnings", author_cents, "sale"
        )
        author_entry["purchase_id"] = inserted.inserted_id
        await db.ledger.insert_one(buyer_entry, session=session)
        await db.ledger.insert_one(author_entry, session=session)

    try:
        await run_transaction(apply_purchase)
        return {"success": True, "message": "Article unlocked"}
    except InsufficientFunds:
        return {
            "success": False,
            "message": "Insufficient wallet balance",
            "status_code": 402,
        }
    except DuplicateKeyError:
        return {
            "success": False,
            "message": "You already own this article",
            "status_code": 409,
        }
    except Exception as e:
        print(f"MONEY ERROR PURCHASING {article['_id']} by {buyer['_id']}: {e}")
        return {"success": False, "message": "Purchase failed", "status_code": 500}


#--- helpers ---

async def run_transaction(callback):
    client = get_db_client()
    async with await client.start_session() as session:
        await session.with_transaction(callback)


#--- builders ---

def split_sale(price_cents):
    author_cents = (price_cents * AUTHOR_SHARE_PERCENT + 50) // 100
    return author_cents, price_cents - author_cents


def build_ledger_entry(user_id, balance, amount_cents, entry_type):
    return {
        "user_id": user_id,
        "balance": balance,
        "amount_cents": amount_cents,
        "type": entry_type,
        "created_at": datetime.now(timezone.utc),
    }


def build_purchase_doc(buyer_id, article, author_cents, platform_cents):
    return {
        "buyer_id": buyer_id,
        "article_id": article["_id"],
        "author_id": article["author_id"],
        "price_cents": article["price_cents"],
        "author_cents": author_cents,
        "platform_cents": platform_cents,
        "created_at": datetime.now(timezone.utc),
    }
