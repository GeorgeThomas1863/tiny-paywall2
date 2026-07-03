import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from db.connection import get_db

SESSION_LIFETIME_DAYS = 30


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError as e:
        print(f"BCRYPT VERIFY ERROR: {e}")
        return False


async def create_session(user_id):
    session_doc = build_session_doc(user_id)
    try:
        await get_db().sessions.insert_one(session_doc)
        return session_doc["_id"]
    except Exception as e:
        print(f"MONGO ERROR CREATING SESSION for user {user_id}: {e}")
        return None


async def destroy_session(token):
    if not token:
        return {"success": False, "message": "No session token"}
    try:
        await get_db().sessions.delete_one({"_id": token})
        return {"success": True, "message": "Logged out"}
    except Exception as e:
        print(f"MONGO ERROR DESTROYING SESSION: {e}")
        return {"success": False, "message": "Failed to log out"}


#---

def build_session_doc(user_id):
    now = datetime.now(timezone.utc)
    return {
        "_id": secrets.token_urlsafe(32),
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + timedelta(days=SESSION_LIFETIME_DAYS),
    }
