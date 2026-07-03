import os

import stripe
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from money.operations import credit_topup

router = APIRouter()


#--- routes ---

@router.post("/stripe/webhook")
async def handle_stripe_webhook(request: Request):
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    event = verify_stripe_signature(payload, signature_header)

    if event["type"] != "checkout.session.completed":
        return {"success": True, "message": "Event ignored"}

    result = await credit_wallet_from_event(event)
    if not result["success"]:
        # Non-2xx makes Stripe retry the event later.
        raise HTTPException(status_code=500, detail=result["message"])
    return result


#--- helpers ---

def verify_stripe_signature(payload, signature_header):
    try:
        return stripe.Webhook.construct_event(
            payload, signature_header, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except Exception as e:
        print(f"STRIPE WEBHOOK SIGNATURE REJECTED: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")


async def credit_wallet_from_event(event):
    checkout_session = event["data"]["object"]
    metadata = read_stripe_key(checkout_session, "metadata")
    user_id = read_stripe_key(metadata, "user_id")
    amount_cents = read_stripe_key(metadata, "amount_cents")

    if not user_id or not amount_cents:
        print(f"STRIPE WEBHOOK MISSING WALLET METADATA on {read_stripe_key(checkout_session, 'id')}")
        return {"success": True, "message": "No wallet metadata — ignored"}

    return await credit_topup(ObjectId(user_id), int(amount_cents), checkout_session["id"])


def read_stripe_key(stripe_object, key):
    # StripeObject (v15+) is not a dict: it has __getitem__/__contains__ but no .get()
    if stripe_object is None or key not in stripe_object:
        return None
    return stripe_object[key]
