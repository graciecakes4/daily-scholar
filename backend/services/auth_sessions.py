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

# how stale last_seen_at has to be before we bother writing it again.
# avoids an UPDATE on every single request while still keeping the
# session-list UI's "active N min ago" reasonably fresh.
SESSION_LAST_SEEN_THROTTLE = timedelta(minutes=15)


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

        # detach the user BEFORE the last_seen_at write below.
        #
        # commit() expires every instance still in the identity map
        # (expire_on_commit defaults to True on our sessionmaker), and an
        # instance that is expired and *then* expunged can never reload
        # itself — the caller gets DetachedInstanceError on the first
        # attribute read. Expunging first takes `user` out of the identity
        # map so the session-row write cannot strand it.
        #
        # The rest of this codebase solves the same problem with
        # commit() -> refresh(obj) -> expunge(obj) (see services/scopes.py).
        # That works too, but here `user` is not the object being written —
        # `row` is — so refreshing it would re-read a row we already have
        # purely to undo an expiry we caused, and it would add a failure
        # mode: a concurrently deleted user turns refresh() into
        # ObjectDeletedError, i.e. a 500 on a path that already has a
        # clean "user is None" branch above. Expunging first has no such
        # window.
        session.expunge(user)

        # throttled last_seen_at write — only touch the row if it's stale
        # by more than SESSION_LAST_SEEN_THROTTLE, so a chatty client
        # doesn't turn into an UPDATE per request
        if row.last_seen_at is None or (now - row.last_seen_at) > SESSION_LAST_SEEN_THROTTLE:
            row.last_seen_at = now
            session.commit()

        return user
    finally:
        session.close()


def list_sessions_for_user(user_id_int: int) -> list[Session]:
    """
    Active (not revoked, not expired) sessions for a user, most-recently-
    active first — powers /settings/account/sessions. Rows are detached
    so callers can read fields after the DB session closes.
    """
    now = datetime.utcnow()
    session = get_session()
    try:
        rows = (
            session.query(Session)
            .filter(
                Session.user_id == user_id_int,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
            # nulls-last "most recently active" ordering: sqlite and
            # postgres both sort NULL first on ASC, last on DESC, so a
            # plain DESC on last_seen_at already puts never-seen rows at
            # the bottom, then falls back to created_at for ties/nulls
            .order_by(Session.last_seen_at.desc(), Session.created_at.desc())
            .all()
        )
        for r in rows:
            session.expunge(r)
        return rows
    finally:
        session.close()


def revoke_session_by_id(session_id: int, owner_user_id_int: int) -> Optional[str]:
    """
    Revoke one session by its row id, scoped to `owner_user_id_int` so a
    user can only revoke their own sessions. Returns the revoked row's
    token (so the caller can tell whether it just killed the request's
    own cookie) or None if no matching active session was found —
    privacy-through-indistinguishability, same 404-shape as friendzone's
    equivalent endpoint: "not found" and "not yours" look identical.
    """
    session = get_session()
    try:
        row = (
            session.query(Session)
            .filter(
                Session.id == session_id,
                Session.user_id == owner_user_id_int,
                Session.revoked_at.is_(None),
            )
            .first()
        )
        if row is None:
            return None
        row.revoked_at = datetime.utcnow()
        token = row.token
        session.commit()
        return token
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
