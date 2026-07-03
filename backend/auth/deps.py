from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request

from db.connection import get_db


async def optional_auth(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None

    session = await find_live_session(token)
    if session is None:
        return None

    return await find_user_by_id(session["user_id"])


async def require_auth(user=Depends(optional_auth)):
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(user=Depends(require_auth)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


#---

async def find_live_session(token):
    try:
        session = await get_db().sessions.find_one({"_id": token})
    except Exception as e:
        print(f"MONGO ERROR FINDING SESSION: {e}")
        return None

    if session is None:
        return None
    # TTL deletion can lag up to 60s; enforce expiry explicitly
    if session["expires_at"] <= datetime.now(timezone.utc):
        return None
    return session


async def find_user_by_id(user_id):
    try:
        return await get_db().users.find_one({"_id": user_id})
    except Exception as e:
        print(f"MONGO ERROR FINDING USER {user_id}: {e}")
        return None
