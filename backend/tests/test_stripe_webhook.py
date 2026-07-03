import hashlib
import hmac
import json
import os
import time

from db.connection import get_db
from tests.helpers import register_user

ALICE = ("alice@test.com", "Alice")


#--- helpers ---

def sign_payload(payload, secret):
    timestamp = int(time.time())
    signed_content = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_content, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def build_checkout_event(user_id, amount_cents, session_id):
    return json.dumps({
        "id": "evt_test_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "metadata": {"user_id": str(user_id), "amount_cents": str(amount_cents)},
            }
        },
    }).encode()


async def post_webhook(client, payload, secret=None):
    secret = secret or os.environ["STRIPE_WEBHOOK_SECRET"]
    return await client.post(
        "/stripe/webhook",
        content=payload,
        headers={"stripe-signature": sign_payload(payload, secret)},
    )


#--- tests ---

async def test_valid_event_credits_wallet(client):
    alice = await register_user(client, *ALICE)
    payload = build_checkout_event(alice["_id"], 500, "cs_webhook_1")

    response = await post_webhook(client, payload)

    assert response.status_code == 200
    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 500

    entry = await get_db().ledger.find_one({"stripe_session_id": "cs_webhook_1"})
    assert entry["type"] == "topup"
    assert entry["amount_cents"] == 500


async def test_replayed_event_credits_exactly_once(client):
    alice = await register_user(client, *ALICE)
    payload = build_checkout_event(alice["_id"], 500, "cs_webhook_replay")

    first = await post_webhook(client, payload)
    second = await post_webhook(client, payload)

    assert first.status_code == 200
    assert second.status_code == 200

    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 500
    assert await get_db().ledger.count_documents({}) == 1


async def test_tampered_signature_rejected(client):
    alice = await register_user(client, *ALICE)
    payload = build_checkout_event(alice["_id"], 500, "cs_webhook_bad")

    response = await post_webhook(client, payload, secret="whsec_wrong_secret")

    assert response.status_code == 400
    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 0


async def test_missing_signature_rejected(client):
    alice = await register_user(client, *ALICE)
    payload = build_checkout_event(alice["_id"], 500, "cs_webhook_nosig")

    response = await client.post("/stripe/webhook", content=payload)

    assert response.status_code == 400


async def test_unhandled_event_type_ignored(client):
    alice = await register_user(client, *ALICE)
    payload = json.dumps({
        "id": "evt_test_2",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_1", "object": "payment_intent"}},
    }).encode()

    response = await post_webhook(client, payload)

    assert response.status_code == 200
    user = await get_db().users.find_one({"_id": alice["_id"]})
    assert user["wallet_cents"] == 0
    assert await get_db().ledger.count_documents({}) == 0
