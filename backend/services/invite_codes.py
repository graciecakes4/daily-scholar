"""
Invite-code lifecycle: generate, validate-and-redeem, revoke.

Shared by `backend/api/admin_invites.py` (admin CRUD) and
`backend/api/auth.py` (the signup-time redemption call). Keeping the
state machine in one place means a code revoked via the admin UI is
immediately rejected at signup with the same reason string the admin
saw — no drift between surfaces.

The redemption flow is atomic against `InviteCode.uses` so a single-use
code can't be double-redeemed by two concurrent signups.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ..database import InviteCode, get_session

logger = logging.getLogger(__name__)


# 12 urlsafe chars from 9 bytes ≈ 70 bits of entropy — unguessable, and
# short enough to share over text/voice without trauma.
INVITE_CODE_BYTES = 9


# ---------------------------------------------------------------------------
# Failure reasons
# ---------------------------------------------------------------------------


class InviteCodeError(ValueError):
    """Base for all signup-time invite validation failures."""


class InviteCodeUnknown(InviteCodeError):
    """The code doesn't exist."""


class InviteCodeRevoked(InviteCodeError):
    """The admin revoked this code."""


class InviteCodeExpired(InviteCodeError):
    """The code's expires_at has passed."""


class InviteCodeExhausted(InviteCodeError):
    """The code's uses has reached max_uses."""


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def _new_code_string() -> str:
    """Generate a unique-looking urlsafe code. Caller checks DB uniqueness."""
    return secrets.token_urlsafe(INVITE_CODE_BYTES)


def generate_invite_code(
    created_by_user_id: int,
    *,
    expires_at: Optional[datetime] = None,
    max_uses: int = 1,
) -> InviteCode:
    """
    Mint a new invite code. Retries on the (astronomically unlikely)
    chance the random string collides with an existing code.
    """
    if max_uses < 1:
        raise ValueError("max_uses must be >= 1")

    session = get_session()
    try:
        # tiny retry loop in case secrets ever returns a dup (won't happen at
        # this entropy, but loops are cheap and the alternative is a 500)
        for _ in range(5):
            candidate = _new_code_string()
            existing = (
                session.query(InviteCode)
                .filter(InviteCode.code == candidate)
                .first()
            )
            if existing is not None:
                continue
            row = InviteCode(
                code=candidate,
                created_by_user_id=created_by_user_id,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                max_uses=max_uses,
                uses=0,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row
        raise RuntimeError("failed to generate a unique invite code after 5 attempts")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Validate + redeem
# ---------------------------------------------------------------------------


@dataclass
class RedeemedInvite:
    """Minimal view of an invite returned after a successful redemption."""

    id: int
    code: str
    uses: int
    max_uses: int


def validate_and_redeem(
    code: str,
    *,
    redeeming_user_id_int: int,
    session: Optional[DbSession] = None,
) -> RedeemedInvite:
    """
    Atomically check that the code is usable and increment its `uses`.

    Pass an existing `session` (typically the same one that's about to
    insert the new User row) to keep the redemption + user-creation in a
    single transaction. Without it we open + commit our own session and
    the user creation could fail after we've already incremented uses.

    Raises a typed InviteCodeError subclass on failure; on success returns
    a RedeemedInvite snapshot.
    """
    if not code or not code.strip():
        raise InviteCodeUnknown("invite code is required")

    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # Lock the row for the duration of the redemption. SQLite ignores
        # the FOR UPDATE hint (single-writer anyway); Postgres honors it
        # and serializes concurrent redemptions of the same code.
        query = session.query(InviteCode).filter(InviteCode.code == code.strip())
        try:
            row = query.with_for_update().first()
        except Exception:
            # dialect doesn't support FOR UPDATE (sqlite) — fall back
            row = query.first()

        if row is None:
            raise InviteCodeUnknown("unknown invite code")
        if row.revoked_at is not None:
            raise InviteCodeRevoked("invite code has been revoked")
        if row.expires_at is not None and row.expires_at <= datetime.utcnow():
            raise InviteCodeExpired("invite code has expired")
        if row.uses >= row.max_uses:
            raise InviteCodeExhausted("invite code has been fully redeemed")

        row.uses += 1
        row.last_redeemed_by_user_id = redeeming_user_id_int
        # stamp `redeemed_at` on the final redemption so the admin UI can
        # render "used X ago" without recomputing — still updates each
        # redemption for multi-use codes
        row.redeemed_at = datetime.utcnow()

        if own_session:
            session.commit()
            session.refresh(row)

        return RedeemedInvite(
            id=row.id,
            code=row.code,
            uses=row.uses,
            max_uses=row.max_uses,
        )
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# Admin operations: list, revoke, delete
# ---------------------------------------------------------------------------


def list_invite_codes(*, include_revoked: bool = True) -> list[InviteCode]:
    """All invite codes, newest first. Used by the admin UI."""
    session = get_session()
    try:
        q = session.query(InviteCode).order_by(InviteCode.created_at.desc())
        if not include_revoked:
            q = q.filter(InviteCode.revoked_at.is_(None))
        rows = q.all()
        for r in rows:
            session.expunge(r)
        return rows
    finally:
        session.close()


def revoke_invite_code(invite_id: int) -> bool:
    """
    Mark a code revoked. Idempotent: returns False when the row was
    already revoked or doesn't exist, True when we flipped it.
    """
    session = get_session()
    try:
        row = (
            session.query(InviteCode)
            .filter(InviteCode.id == invite_id, InviteCode.revoked_at.is_(None))
            .first()
        )
        if row is None:
            return False
        row.revoked_at = datetime.utcnow()
        session.commit()
        return True
    finally:
        session.close()
