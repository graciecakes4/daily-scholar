"""
Server-side session CRUD.

Shared by `backend/api/auth.py` (login/logout) and `backend/auth.py`
(the per-request identity dependency) so both go through the same
expire / revoke logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ..database import Session, User, get_session
from .auth_security import generate_session_token


# Sessions live 30 days by default. Long enough for "stay logged in"
# behavior on a PWA, short enough that a leaked cookie has a finite
# blast radius without the user noticing.
DEFAULT_SESSION_TTL_DAYS = 30


def create_session(
    user_id_int: int,
    *,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    ttl_days: int = DEFAULT_SESSION_TTL_DAYS,
) -> str:
    """
    Mint a new session row for a user. Returns the token to set in the cookie.
    """
    now = datetime.utcnow()
    token = generate_session_token()
    session = get_session()
    try:
        row = Session(
            token=token,
            user_id=user_id_int,
            created_at=now,
            expires_at=now + timedelta(days=ttl_days),
            user_agent=(user_agent or "")[:500],
            ip=(ip or "")[:64],
        )
        session.add(row)
        session.commit()
    finally:
        session.close()
    return token


def lookup_session_user(token: str) -> Optional[User]:
    """
    Resolve a session token to the owning User, or None if the token is
    unknown, expired, or revoked. Detaches the User row from the session so
    callers can read attributes after we close the DB session.

    NOTE: does NOT enforce user.status — the auth dependency layer decides
    how to react to a `pending` or `suspended` user holding a valid token
    (we want different status codes / messages for each).
    """
    if not token:
        return None

    now = datetime.utcnow()
    session = get_session()
    try:
        row = (
            session.query(Session)
            .filter(Session.token == token)
            .first()
        )
        if row is None:
            return None
        if row.revoked_at is not None:
            return None
        if row.expires_at <= now:
            return None
        user = session.query(User).filter(User.id == row.user_id).first()
        if user is None:
            # session pointing to a deleted user — clean up the row
            session.delete(row)
            session.commit()
            return None
        # detach so the caller can read fields after the session closes
        session.expunge(user)
        return user
    finally:
        session.close()


def revoke_session(token: str) -> bool:
    """
    Mark a session revoked. Idempotent: returns False if the token was
    already unknown or revoked, True if we actually flipped it.
    """
    if not token:
        return False
    session = get_session()
    try:
        row = (
            session.query(Session)
            .filter(Session.token == token, Session.revoked_at.is_(None))
            .first()
        )
        if row is None:
            return False
        row.revoked_at = datetime.utcnow()
        session.commit()
        return True
    finally:
        session.close()


def revoke_all_sessions_for_user(user_id_int: int) -> int:
    """
    Revoke every active session for a user. Used when an admin suspends
    them or when an admin resets their password. Returns count revoked.
    """
    return _revoke_sessions(user_id_int, except_token=None)


def revoke_other_sessions_for_user(user_id_int: int, except_token: str) -> int:
    """
    Revoke every active session for a user EXCEPT the one identified by
    `except_token`. Used after a self-service password change so the
    actor's current session stays alive while any other (potentially
    hijacked) device gets kicked out.
    """
    return _revoke_sessions(user_id_int, except_token=except_token)


def _revoke_sessions(user_id_int: int, *, except_token: Optional[str]) -> int:
    now = datetime.utcnow()
    session = get_session()
    try:
        q = (
            session.query(Session)
            .filter(
                Session.user_id == user_id_int,
                Session.revoked_at.is_(None),
            )
        )
        if except_token:
            q = q.filter(Session.token != except_token)
        rows = q.all()
        for r in rows:
            r.revoked_at = now
        session.commit()
        return len(rows)
    finally:
        session.close()
