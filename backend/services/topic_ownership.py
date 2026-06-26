"""
Topic ownership helpers (Phase C).

Three concerns live here:

  1. Generating opaque ids for user-created topics so two users can each
     have a topic named "ML Papers" without slug collisions.

  2. Resolving a caller's `user_id` string into the integer User.id used
     in `topics.owner_user_id` (the existing 9 user-scoped tables key on
     the string `user_id`, but the topics FK keys on the int `users.id`
     — these helpers bridge the two).

  3. Permission helpers (`can_view_topic`, `can_edit_topic`) so endpoints
     and queries share the same logic and can't drift apart.

Solo dev (`__local__`) is handled specially throughout: there's no User
row for the sentinel, so it can't own topics in the FK sense, but it
behaves like an admin for permission checks. This preserves the
pre-Phase-C "solo sees and edits everything" experience.
"""

from __future__ import annotations

import secrets
from typing import Optional

from ..auth import lookup_user_by_user_id
from ..database import (
    DEFAULT_USER_ID,
    USER_ROLE_ADMIN,
    Topic,
    User,
)


# user-topic id format: short prefix + 6 base32 chars (~30 bits entropy)
# eg "usr-a3kf2q". prefix makes them visually distinct from yaml slugs
# (`photometric_classification`) and disqualifies the entire `usr-` slug
# namespace from yaml bootstrap (defensive — caller could reject those at
# yaml load time too).
USER_TOPIC_ID_PREFIX = "usr-"


def generate_user_topic_id() -> str:
    """Make a fresh opaque id for a user-owned topic."""
    # token_hex(4) → 8 hex chars; trim to 6 for a friendly 10-char total.
    # Collision odds are negligible at expected scale.
    return f"{USER_TOPIC_ID_PREFIX}{secrets.token_hex(4)[:6]}"


def is_user_topic_id(topic_id: str) -> bool:
    """True if `topic_id` was auto-generated (vs a human yaml slug)."""
    return isinstance(topic_id, str) and topic_id.startswith(USER_TOPIC_ID_PREFIX)


# ---------------------------------------------------------------------------
# Caller resolution
# ---------------------------------------------------------------------------


def resolve_caller(user_id_string: str) -> tuple[Optional[User], bool]:
    """
    Look up the calling user. Returns (User-row-or-None, is_admin_bool).

      * solo `__local__` → (None, True)         — sentinel treated as admin
      * real user        → (User, role == admin)
      * unknown user_id  → (None, False)        — CF Access email that
                                                   hasn't signed up in-app
    """
    if user_id_string == DEFAULT_USER_ID:
        return None, True
    user = lookup_user_by_user_id(user_id_string)
    if user is None:
        return None, False
    return user, user.role == USER_ROLE_ADMIN


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


def can_view_topic(topic: Topic, caller: Optional[User], is_admin: bool) -> bool:
    """
    True if the caller is allowed to see this topic.

      * system topic (owner is NULL)   → everyone can see
      * admin                          → can see everything
      * solo (caller=None, is_admin=True) → can see everything
      * owner                          → can see their own
      * public topic owned by someone else → can see (Phase D may
        further restrict via blocks / subscriptions, but in Phase C
        public means everyone-visible)
      * private topic owned by someone else → hidden
    """
    if topic.owner_user_id is None:
        return True
    if is_admin:
        return True
    if topic.visibility == "public":
        return True
    if caller is not None and topic.owner_user_id == caller.id:
        return True
    return False


def can_edit_topic(topic: Topic, caller: Optional[User], is_admin: bool) -> bool:
    """
    True if the caller is allowed to mutate this topic.

      * admin (incl. solo)        → can edit anything
      * owner                     → can edit their own
      * everyone else             → cannot
    """
    if is_admin:
        return True
    if topic.owner_user_id is None:
        # system topic, non-admin → no
        return False
    return caller is not None and topic.owner_user_id == caller.id


def caller_owner_id(caller: Optional[User], is_admin: bool) -> Optional[int]:
    """
    Default owner_user_id stamped on POST /topics for this caller.

    Solo / admin: defaults to None (system topic). Regular users: their
    own id. Admins can override to a specific user id (or NULL) via the
    request body if the endpoint exposes that.
    """
    if is_admin:
        return None     # admins / solo default to creating system topics
    if caller is None:
        return None     # shouldn't happen at endpoint level (auth required)
    return caller.id


# ---------------------------------------------------------------------------
# Visibility default
# ---------------------------------------------------------------------------


def default_visibility(owner_user_id: Optional[int]) -> str:
    """
    Sensible default visibility when the caller doesn't specify.

    System topics (NULL owner) → public; user topics → private.
    """
    return "public" if owner_user_id is None else "private"
