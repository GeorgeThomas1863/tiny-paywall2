import os

import stripe
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from auth.deps import require_auth
from config import get_frontend_url
from db.connection import get_db

router = APIRouter()

# Mirrored in frontend/src/pages/AccountPage.jsx TOPUP_OPTIONS_CENTS — keep in sync.
TOPUP_AMOUNTS_CENTS = (500, 1000, 2000)


class TopupBody(BaseModel):
    amount_cents: int


#--- routes ---

@router.post("/wallet/topup")
async def create_topup(body: TopupBody, user=Depends(require_auth)):
    reject_invalid_topup_amount(body.amount_cents)

    # Stripe's SDK is synchronous — run it off the event loop.
    url = await run_in_threadpool(create_checkout_session, user["_id"], body.amount_cents)
    return {"success": True, "message": "Checkout session created", "url": url}


@router.get("/wallet/history")
async def get_wallet_history(user=Depends(require_auth)):
    entries = await find_ledger_entries(user["_id"])

    items = []
    for entry in entries:
        items.append(serialize_ledger_entry(entry))
    return items


#--- helpers ---

def reject_invalid_topup_amount(amount_cents):
    if amount_cents not in TOPUP_AMOUNTS_CENTS:
        allowed = ", ".join(str(amount) for amount in TOPUP_AMOUNTS_CENTS)
        raise HTTPException(status_code=422, detail=f"Top-up must be one of: {allowed} cents")


def create_checkout_session(user_id, amount_cents):
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    frontend_url = get_frontend_url()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[build_topup_line_item(amount_cents)],
            metadata={"user_id": str(user_id), "amount_cents": str(amount_cents)},
            success_url=f"{frontend_url}/account?topup=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_url}/account",
        )
        return session.url
    except Exception as e:
        print(f"STRIPE ERROR CREATING CHECKOUT for {user_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to create checkout session")


async def find_ledger_entries(user_id):
    try:
        cursor = get_db().ledger.find({"user_id": user_id}).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LOADING LEDGER for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load history")


#--- builders ---

def build_topup_line_item(amount_cents):
    return {
        "quantity": 1,
        "price_data": {
            "currency": "usd",
            "unit_amount": amount_cents,
            "product_data": {"name": "Wallet top-up"},
        },
    }


def serialize_ledger_entry(entry):
    item = {
        "id": str(entry["_id"]),
        "type": entry["type"],
        "balance": entry["balance"],
        "amount_cents": entry["amount_cents"],
        "created_at": entry["created_at"].isoformat(),
    }
    if "stripe_session_id" in entry:
        item["stripe_session_id"] = entry["stripe_session_id"]
    return item
