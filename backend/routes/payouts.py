from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import require_admin, require_auth
from db.connection import get_db
from money.operations import reserve_payout, return_payout
from routes.articles import parse_object_id

router = APIRouter()

DESTINATION_MAX_LENGTH = 200
PAYOUT_STATUSES = ("requested", "paid", "rejected")
RESOLVE_STATUSES = ("paid", "rejected")


class PayoutRequestBody(BaseModel):
    destination: str


class PayoutResolveBody(BaseModel):
    status: str


#--- routes ---

@router.post("/payouts/request")
async def request_payout(body: PayoutRequestBody, user=Depends(require_auth)):
    destination = validate_destination(body.destination)
    await reject_pending_request(user["_id"])

    # The transaction enforces the $10 threshold atomically (SPEC §2.4).
    result = await reserve_payout(user["_id"], destination)
    if not result["success"]:
        raise HTTPException(status_code=result["status_code"], detail=result["message"])
    return result


@router.get("/payouts/mine")
async def list_my_payouts(user=Depends(require_auth)):
    requests = await find_payout_requests({"user_id": user["_id"]})

    items = []
    for request in requests:
        items.append(serialize_payout_request(request))
    return items


@router.get("/payouts")
async def list_all_payouts(status: str | None = None, user=Depends(require_admin)):
    query = build_status_query(status)
    requests = await find_payout_requests(query)
    requesters = await map_requesters(requests)

    items = []
    for request in requests:
        items.append(serialize_admin_payout_request(request, requesters))
    return items


@router.put("/payouts/{request_id}")
async def resolve_payout(request_id: str, body: PayoutResolveBody, user=Depends(require_admin)):
    validate_resolve_status(body.status)
    request = await find_payout_or_404(request_id)

    if body.status == "paid":
        return await mark_request_paid(request["_id"])
    return await reject_request(request["_id"])


#--- guards / validation ---

def validate_destination(destination):
    destination = destination.strip()
    if not destination or len(destination) > DESTINATION_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Destination must be 1-{DESTINATION_MAX_LENGTH} characters",
        )
    return destination


async def reject_pending_request(user_id):
    try:
        pending = await get_db().payout_requests.count_documents(
            {"user_id": user_id, "status": "requested"}
        )
    except Exception as e:
        print(f"MONGO ERROR COUNTING PENDING PAYOUTS for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to request payout")

    if pending > 0:
        raise HTTPException(status_code=409, detail="You already have a pending payout request")


def validate_resolve_status(status):
    if status not in RESOLVE_STATUSES:
        raise HTTPException(status_code=422, detail="Status must be paid or rejected")


def build_status_query(status):
    if status is None:
        return {}
    if status not in PAYOUT_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"Status filter must be one of: {', '.join(PAYOUT_STATUSES)}"
        )
    return {"status": status}


#--- queries ---

async def find_payout_requests(query):
    try:
        cursor = get_db().payout_requests.find(query).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LISTING PAYOUTS {query}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load payout requests")


async def find_payout_or_404(request_id):
    object_id = parse_object_id(request_id)
    if object_id is None:
        raise HTTPException(status_code=404, detail="Payout request not found")

    try:
        request = await get_db().payout_requests.find_one({"_id": object_id})
    except Exception as e:
        print(f"MONGO ERROR FINDING PAYOUT {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load payout request")

    if request is None:
        raise HTTPException(status_code=404, detail="Payout request not found")
    return request


async def map_requesters(requests):
    user_ids = list({request["user_id"] for request in requests})
    if not user_ids:
        return {}

    try:
        cursor = get_db().users.find(
            {"_id": {"$in": user_ids}}, {"email": 1, "display_name": 1}
        )
        users = await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR MAPPING PAYOUT REQUESTERS: {e}")
        raise HTTPException(status_code=500, detail="Failed to load payout requests")

    requesters = {}
    for requester in users:
        requesters[requester["_id"]] = requester
    return requesters


#--- operations ---

async def mark_request_paid(request_id):
    # Paid moves no money (it already left on reserve) — status flip only (SPEC §2.4).
    try:
        result = await get_db().payout_requests.update_one(
            {"_id": request_id, "status": "requested"},
            {"$set": {"status": "paid", "resolved_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        print(f"MONGO ERROR MARKING PAYOUT PAID {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve payout")

    if result.matched_count == 0:
        raise HTTPException(status_code=409, detail="Request already resolved")
    return {"success": True, "message": "Payout marked paid"}


async def reject_request(request_id):
    result = await return_payout(request_id)
    if not result["success"]:
        raise HTTPException(status_code=result["status_code"], detail=result["message"])
    return result


#--- builders ---

def serialize_payout_request(request):
    return {
        "id": str(request["_id"]),
        "amount_cents": request["amount_cents"],
        "destination": request["destination"],
        "status": request["status"],
        "created_at": request["created_at"].isoformat(),
        "resolved_at": request["resolved_at"].isoformat() if request["resolved_at"] else None,
    }


def serialize_admin_payout_request(request, requesters):
    item = serialize_payout_request(request)
    requester = requesters.get(request["user_id"], {})
    item["email"] = requester.get("email", "unknown")
    item["display_name"] = requester.get("display_name", "Unknown")
    return item
