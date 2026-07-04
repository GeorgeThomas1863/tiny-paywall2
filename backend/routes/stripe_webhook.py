import os

import stripe
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Request

from money.operations import credit_topup
from routes.wallet import TOPUP_AMOUNTS_CENTS

router = APIRouter()

CREDIT_EVENT_TYPES = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
)


#--- routes ---

@router.post("/stripe/webhook")
async def handle_stripe_webhook(request: Request):
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    event = verify_stripe_signature(payload, signature_header)

    if event["type"] not in CREDIT_EVENT_TYPES:
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
    topup = parse_topup_details(checkout_session)
    if topup is None:
        return {"success": True, "message": "Not a valid wallet top-up — ignored"}

    return await credit_topup(
        topup["user_id"], topup["amount_cents"], checkout_session["id"]
    )


def parse_topup_details(checkout_session):
    # Every guard here protects money invariant 5 (SPEC §10): credit only
    # validated preset amounts that were actually paid, for a parseable user.
    session_id = read_stripe_key(checkout_session, "id")

    if read_stripe_key(checkout_session, "payment_status") != "paid":
        print(f"STRIPE WEBHOOK: session {session_id} not paid — ignored")
        return None

    metadata = read_stripe_key(checkout_session, "metadata")
    raw_user_id = read_stripe_key(metadata, "user_id")
    raw_amount = read_stripe_key(metadata, "amount_cents")
    if not raw_user_id or not raw_amount:
        print(f"STRIPE WEBHOOK: session {session_id} has no wallet metadata — ignored")
        return None

    parsed = parse_topup_values(raw_user_id, raw_amount)
    if parsed is None:
        print(f"STRIPE WEBHOOK: session {session_id} has malformed metadata — ignored")
        return None

    user_id, amount_cents = parsed
    if amount_cents not in TOPUP_AMOUNTS_CENTS:
        print(f"STRIPE WEBHOOK: session {session_id} non-preset amount {amount_cents} — ignored")
        return None

    amount_total = read_stripe_key(checkout_session, "amount_total")
    if amount_cents != amount_total:
        print(
            f"STRIPE WEBHOOK: session {session_id} metadata amount {amount_cents} "
            f"!= paid amount {amount_total} — ignored"
        )
        return None

    return {"user_id": user_id, "amount_cents": amount_cents}


#--- builders ---

def parse_topup_values(raw_user_id, raw_amount):
    try:
        return ObjectId(raw_user_id), int(raw_amount)
    except (InvalidId, TypeError, ValueError):
        return None


def read_stripe_key(stripe_object, key):
    # StripeObject (v15+) is not a dict: it has __getitem__/__contains__ but no .get()
    if stripe_object is None or key not in stripe_object:
        return None
    return stripe_object[key]
