import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from auth.deps import require_auth
from auth.rate_limit import check_rate_limit, clear_attempts, record_failed_attempt
from auth.security import (
    SESSION_LIFETIME_DAYS,
    create_session,
    destroy_session,
    hash_password,
    verify_password,
)
from config import get_frontend_url
from db.connection import get_db

router = APIRouter()

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8
DISPLAY_NAME_MAX_LENGTH = 40
LOGIN_FAILED_MESSAGE = "Invalid email or password"


class RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str


class LoginBody(BaseModel):
    email: str
    password: str


class RenameBody(BaseModel):
    display_name: str


#--- routes ---

@router.post("/auth/register")
async def register_user(body: RegisterBody, request: Request, response: Response):
    enforce_rate_limit(request)

    email = normalize_email(body.email)
    display_name = body.display_name.strip()
    reject_invalid_registration(email, body.password, display_name)

    user_id = await insert_user(email, body.password, display_name)
    await start_session(user_id, response)
    return {"success": True, "message": "Account created"}


@router.post("/auth/login")
async def login_user(body: LoginBody, request: Request, response: Response):
    enforce_rate_limit(request)

    user = await find_user_by_email(normalize_email(body.email))
    if user is None or not verify_password(body.password, user["password_hash"]):
        record_failed_attempt(get_client_ip(request))
        raise HTTPException(status_code=401, detail=LOGIN_FAILED_MESSAGE)

    clear_attempts(get_client_ip(request))
    await start_session(user["_id"], response)
    return {"success": True, "message": "Logged in"}


@router.post("/auth/logout")
async def logout_user(request: Request, response: Response, user=Depends(require_auth)):
    result = await destroy_session(request.cookies.get("session"))
    clear_session_cookie(response)
    return result


@router.get("/auth/me")
async def get_me(user=Depends(require_auth)):
    return serialize_user(user)


@router.put("/auth/me")
async def rename_me(body: RenameBody, user=Depends(require_auth)):
    display_name = body.display_name.strip()
    reject_invalid_display_name(display_name)

    await update_display_name(user["_id"], display_name)
    return {"success": True, "message": "Display name updated"}


#--- helpers ---

def enforce_rate_limit(request):
    if not check_rate_limit(get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def reject_invalid_registration(email, password, display_name):
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="Invalid email address")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    reject_invalid_display_name(display_name)


def reject_invalid_display_name(display_name):
    if not display_name or len(display_name) > DISPLAY_NAME_MAX_LENGTH:
        raise HTTPException(status_code=422, detail="Display name must be 1-40 characters")


async def insert_user(email, password, display_name):
    user_doc = build_user_doc(email, password, display_name)
    try:
        result = await get_db().users.insert_one(user_doc)
        return result.inserted_id
    except DuplicateKeyError as e:
        raise build_duplicate_user_error(e)
    except Exception as e:
        print(f"MONGO ERROR INSERTING USER {email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create account")


async def find_user_by_email(email):
    try:
        return await get_db().users.find_one({"email": email})
    except Exception as e:
        print(f"MONGO ERROR FINDING USER {email}: {e}")
        return None


async def update_display_name(user_id, display_name):
    try:
        await get_db().users.update_one(
            {"_id": user_id}, {"$set": {"display_name": display_name}}
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Display name already taken")
    except Exception as e:
        print(f"MONGO ERROR RENAMING USER {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update display name")


async def start_session(user_id, response):
    token = await create_session(user_id)
    if token is None:
        raise HTTPException(status_code=500, detail="Failed to create session")
    set_session_cookie(response, token)


#--- builders ---

def normalize_email(email):
    return email.strip().lower()


def get_client_ip(request):
    if request.client is None:
        return "unknown"
    return request.client.host


def build_user_doc(email, password, display_name):
    return {
        "email": email,
        "display_name": display_name,
        "password_hash": hash_password(password),
        "is_admin": False,
        "wallet_cents": 0,
        "earnings_cents": 0,
        "created_at": datetime.now(timezone.utc),
    }


def build_duplicate_user_error(error):
    if "display_name" in str(error):
        return HTTPException(status_code=409, detail="Display name already taken")
    return HTTPException(status_code=409, detail="Email already registered")


def serialize_user(user):
    return {
        "email": user["email"],
        "display_name": user["display_name"],
        "is_admin": user["is_admin"],
        "wallet_cents": user["wallet_cents"],
        "earnings_cents": user["earnings_cents"],
    }


def set_session_cookie(response, token):
    response.set_cookie(
        "session",
        token,
        max_age=SESSION_LIFETIME_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=get_frontend_url().startswith("https"),
    )


def clear_session_cookie(response):
    response.delete_cookie("session")
