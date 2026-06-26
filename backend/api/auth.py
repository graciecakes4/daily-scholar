"""
In-app authentication endpoints (Phase A foundation).

Flow:
  1. POST /auth/signup → creates a `pending` user. (Phase B adds the
     invite-code gate; Phase A leaves the endpoint open so we can E2E
     test the rest of the chain.)
  2. POST /auth/login → validates credentials, mints a server-side
     session, sets the HttpOnly cookie. Suspended → 403. Pending users
     CAN log in (so they can see their status page) but `get_current_user_id`
     blocks them from every other endpoint.
  3. POST /auth/logout → revokes the session and clears the cookie.
  4. GET /auth/me → returns the current user's profile or 401.

Cookie name is `ds_session`. It's HttpOnly, SameSite=Lax, and Secure when
the app is served over HTTPS (env-gated via SESSION_COOKIE_SECURE so local
HTTP dev still works).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..database import (
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    User,
    get_session,
)
from ..services.auth_security import (
    InvalidEmailError,
    InvalidUserIdError,
    MIN_PASSWORD_LENGTH,
    default_user_id_from_email,
    hash_password,
    validate_email,
    validate_user_id,
    verify_password,
)
from ..services.auth_sessions import (
    create_session,
    lookup_session_user,
    revoke_session,
)
from ..services.invite_codes import (
    InviteCodeError,
    InviteCodeExhausted,
    InviteCodeExpired,
    InviteCodeRevoked,
    InviteCodeUnknown,
    validate_and_redeem,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Cookie config
# ---------------------------------------------------------------------------


SESSION_COOKIE_NAME = "ds_session"


def _cookie_secure() -> bool:
    """Default Secure in production; allow opt-out for local HTTP dev."""
    val = os.environ.get("SESSION_COOKIE_SECURE")
    if val is None:
        # mirror the existing app convention: debug=True implies local dev
        return not get_settings().debug
    return val.strip().lower() in ("1", "true", "yes", "on")


def _set_session_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_cookie_secure(),
        samesite="lax",
        httponly=True,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    """Body for POST /auth/signup."""

    email: str = Field(description="Login email; lowercased on write.")
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        description=f"Plaintext password, at least {MIN_PASSWORD_LENGTH} chars.",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional custom handle. Defaults to the email when omitted.",
    )
    invite_code: Optional[str] = Field(
        default=None,
        description=(
            "Invite code issued by an admin. Required unless the server is "
            "running with OPEN_SIGNUP=1 (local dev only)."
        ),
    )


def _open_signup_enabled() -> bool:
    """Env-gated bypass for local dev: OPEN_SIGNUP=1 disables the invite check."""
    val = os.environ.get("OPEN_SIGNUP", "").strip().lower()
    return val in ("1", "true", "yes", "on")


class LoginRequest(BaseModel):
    email: str
    password: str


class UserProfile(BaseModel):
    """Shape returned by /auth/me and signup/login responses."""

    email: str
    user_id: str
    role: str
    status: str
    # Phase E: false until the wizard runs (or is skipped). The layout
    # uses this to redirect unonboarded users to /onboarding.
    onboarded: bool = True
    created_at: datetime
    last_login_at: Optional[datetime] = None


def _profile(user: User) -> UserProfile:
    return UserProfile(
        email=user.email,
        user_id=user.user_id,
        role=user.role,
        status=user.status,
        onboarded=getattr(user, "onboarded", True),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@auth_router.post("/signup", status_code=201)
def signup(body: SignupRequest, response: Response) -> dict:
    """
    Create a new account in `pending` status. Requires a valid
    `invite_code` issued by an admin, unless the server is running with
    `OPEN_SIGNUP=1` (local dev only — never in production).

    The invite redemption + user insert run in the same DB transaction:
    if the user insert fails (duplicate email, etc.) the invite's
    `uses` counter is NOT incremented. This keeps single-use codes
    usable after a failed first attempt.

    Returns the new user's profile + a hint that admin approval is needed.
    Does NOT log the user in — they have to wait for approval and then
    call /auth/login.
    """
    # normalize + validate up front so we 400 before touching the DB
    try:
        email = validate_email(body.email)
    except InvalidEmailError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if body.user_id is None or not body.user_id.strip():
        user_id = default_user_id_from_email(email)
    else:
        try:
            user_id = validate_user_id(body.user_id)
        except InvalidUserIdError as e:
            raise HTTPException(status_code=400, detail=str(e))

    invite_required = not _open_signup_enabled()
    if invite_required and (body.invite_code is None or not body.invite_code.strip()):
        raise HTTPException(status_code=400, detail="invite code is required")

    session = get_session()
    try:
        # uniqueness checks — return clear errors so the UI can highlight
        # the offending field instead of bubbling a generic IntegrityError
        if session.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=409, detail="An account with that email already exists")
        if session.query(User).filter(User.user_id == user_id).first():
            raise HTTPException(status_code=409, detail="That username is taken")

        user = User(
            email=email,
            user_id=user_id,
            password_hash=hash_password(body.password),
            status=USER_STATUS_PENDING,
            role="user",
            created_at=datetime.utcnow(),
        )
        session.add(user)
        session.flush()        # populate user.id without committing

        # redeem the invite inside the same transaction so a failed user
        # insert (race condition on uniqueness) doesn't burn the code
        if invite_required:
            try:
                validate_and_redeem(
                    body.invite_code or "",
                    redeeming_user_id_int=user.id,
                    session=session,
                )
            except InviteCodeUnknown as e:
                raise HTTPException(status_code=400, detail=str(e))
            except InviteCodeRevoked as e:
                raise HTTPException(status_code=400, detail=str(e))
            except InviteCodeExpired as e:
                raise HTTPException(status_code=400, detail=str(e))
            except InviteCodeExhausted as e:
                raise HTTPException(status_code=400, detail=str(e))
            except InviteCodeError as e:
                raise HTTPException(status_code=400, detail=str(e))

        session.commit()
        session.refresh(user)
        return {
            "profile": _profile(user).model_dump(),
            "message": "Account created. An administrator will review your request shortly.",
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("signup: unexpected failure: %s", e)
        raise HTTPException(status_code=500, detail="Signup failed")
    finally:
        session.close()


@auth_router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    """
    Validate credentials, mint a session, set the cookie.

    Behavior by status:
      - active    → success, cookie set, profile returned.
      - pending   → success, cookie set, profile returned (so the user
                    can see their pending status on /account/pending).
                    Other endpoints will 403 them via get_current_user_id.
      - suspended → 403 with reason; NO cookie set.

    Returns 401 for wrong email + 401 for wrong password (same code so we
    don't leak which one was the miss).
    """
    try:
        email = validate_email(body.email)
    except InvalidEmailError:
        # don't validate-error on login — return the generic 401 so we
        # don't tell an attacker "yes this email format is wrong"
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session = get_session()
    try:
        user = session.query(User).filter(User.email == email).first()
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if user.status == USER_STATUS_SUSPENDED:
            raise HTTPException(
                status_code=403,
                detail="This account has been suspended. Contact the administrator.",
            )

        # mint session, set cookie. pending users get a cookie too — they
        # just can't *do* anything with it on protected endpoints.
        user.last_login_at = datetime.utcnow()
        user_id_int = user.id
        user_status = user.status
        profile = _profile(user)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("login: unexpected failure: %s", e)
        raise HTTPException(status_code=500, detail="Login failed")
    finally:
        session.close()

    # session creation outside the user-fetch session so we don't fight
    # over the same DB connection
    token = create_session(
        user_id_int,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_session_cookie(response, token, max_age_seconds=30 * 24 * 3600)

    return {"profile": profile.model_dump(), "pending": user_status == USER_STATUS_PENDING}


@auth_router.post("/logout")
def logout(
    response: Response,
    ds_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """
    Revoke the session and clear the cookie. Always returns 200 — logout
    is idempotent and we don't want to leak whether a session was valid.
    """
    revoked = False
    if ds_session:
        revoked = revoke_session(ds_session)
    _clear_session_cookie(response)
    return {"ok": True, "revoked": revoked}


@auth_router.get("/me")
def me(
    ds_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """
    Return the current logged-in user's profile, or 401 if no valid
    session. Used by the AuthBoundary on app load to decide whether to
    redirect to /login.
    """
    if not ds_session:
        raise HTTPException(status_code=401, detail="Not logged in")
    user = lookup_session_user(ds_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return {"profile": _profile(user).model_dump()}
