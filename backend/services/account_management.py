"""
Self-service + admin account management:

  * `change_password(user_id, old, new)` — verify old, hash new.
  * `change_password_admin(target_user_id, new, ...)` — skip old check.
  * `change_username(current_user_id, new_user_id)` — cascade rename
    across every user-scoped table.

The username cascade is the meaty one. It's the same logic as
`scripts/reassign_user_id.py` but factored as a service so both the
CLI and the new self-service endpoint share a single implementation.
Adding a table to USER_SCOPED_MODELS is the one place to remember.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession

from ..database import (
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    DailyContentCache,
    PaperPDF,
    PushSubscription,
    SeenPaper,
    TopicSubscription,
    User,
    UserSettings,
    UserStats,
    get_session,
)
from .auth_security import hash_password, verify_password

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tables keyed on the string `user_id`
# ---------------------------------------------------------------------------
#
# Adding a new user-scoped table? Append it here AND to the same list in
# scripts/reassign_user_id.py — both call paths cascade through this list,
# but the CLI imports it via this module so really there's just one source.

USER_SCOPED_MODELS = [
    SeenPaper,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    PaperPDF,
    DailyContentCache,
    UserStats,
    PushSubscription,
    UserSettings,
    TopicSubscription,          # added in Phase D
]


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class AccountError(ValueError):
    """Base class for self-service account mutation failures."""


class WrongPassword(AccountError):
    """The supplied current_password doesn't match the stored hash."""


class UsernameTaken(AccountError):
    """new_user_id collides with another User's user_id."""


class UsernameUnchanged(AccountError):
    """new_user_id equals the current user_id — nothing to do."""


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def change_password(user_id_int: int, old_password: str, new_password: str) -> None:
    """
    Self-service password change. Verifies `old_password` against the
    stored hash and writes the new one. Caller (the endpoint) is
    responsible for any side effects (revoke other sessions, etc.).
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id_int).first()
        if user is None:
            raise AccountError("user not found")
        if not verify_password(old_password, user.password_hash):
            raise WrongPassword("current password is incorrect")
        # `hash_password` validates length itself
        user.password_hash = hash_password(new_password)
        session.commit()
    finally:
        session.close()


def change_password_admin(target_user_id_int: int, new_password: str) -> None:
    """
    Admin password reset. Skips the current-password check. Caller (the
    endpoint) handles authorization + session revocation + audit logging.
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.id == target_user_id_int).first()
        if user is None:
            raise AccountError("user not found")
        user.password_hash = hash_password(new_password)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Username (user_id) — cascade rename
# ---------------------------------------------------------------------------


def change_username(
    current_user_id: str,
    new_user_id: str,
    *,
    session: Optional[DbSession] = None,
) -> dict[str, int]:
    """
    Rename the calling user's `user_id` everywhere it appears.

    Updates `users.user_id` AND cascades to every USER_SCOPED_MODELS table
    in a single transaction. Returns per-table row counts that were moved
    (also includes a `users` entry for the User row itself = 1).

    Raises:
      UsernameUnchanged   — if new == current (caller can ignore)
      UsernameTaken       — if new_user_id is already on another User
      AccountError        — if the current user_id doesn't exist

    Notes on what's NOT touched:
      * sessions — FK to users.id (int); cookie keeps working post-rename.
      * audit log — historical record; actor/target identifiers freeze
        at-the-time of each event.
    """
    if current_user_id == new_user_id:
        raise UsernameUnchanged("new username is identical to the current one")

    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # ensure the source User actually exists
        user = (
            session.query(User)
            .filter(User.user_id == current_user_id)
            .first()
        )
        if user is None:
            raise AccountError(f"user with user_id {current_user_id!r} not found")

        # collision check — the unique constraint on users.user_id would
        # catch this at commit, but we want a typed error before then so
        # the endpoint can map it to a clean 409
        collision = (
            session.query(User)
            .filter(User.user_id == new_user_id, User.id != user.id)
            .first()
        )
        if collision is not None:
            raise UsernameTaken(f"username {new_user_id!r} is already taken")

        # cascade the rename across every user-scoped table. Order matters
        # only if there are FKs between them — there aren't, so the order
        # in USER_SCOPED_MODELS is just for readability.
        counts: dict[str, int] = {}
        for model in USER_SCOPED_MODELS:
            result = session.execute(
                update(model)
                .where(model.user_id == current_user_id)
                .values(user_id=new_user_id)
            )
            counts[model.__tablename__] = int(result.rowcount or 0)

        # finally the users row itself
        user.user_id = new_user_id
        counts["users"] = 1

        if own_session:
            session.commit()
        return counts
    except Exception:
        if own_session:
            session.rollback()
        raise
    finally:
        if own_session:
            session.close()
