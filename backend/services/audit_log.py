"""
Admin audit log helper.

Best-effort by design: a logging failure (DB hiccup, schema drift) MUST
NOT break the underlying admin action. Endpoints call `log_event` after
they've already committed the mutation, and we swallow any exception
into a warning. The audit trail is a "best-effort trace" rather than
a transactional record — we'd rather lose an event than block a suspend.

Event-type constants live here so callers don't typo their way into
silent drift between writes and the Audit Log tab's filter dropdown.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ..auth import lookup_user_by_user_id
from ..database import (
    DEFAULT_USER_ID,
    AdminAuditEvent,
    get_session,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event-type constants
# ---------------------------------------------------------------------------


class EventType:
    """String constants for `admin_audit_log.event_type`."""

    USER_APPROVE = "user.approve"
    USER_REJECT = "user.reject"
    USER_ROLE_CHANGE = "user.role_change"
    USER_SUSPEND = "user.suspend"
    USER_REACTIVATE = "user.reactivate"
    # Admin-triggered password reset. Self-service password changes are
    # NOT audited — they're a user-driven security operation, not an
    # admin mutation worth surfacing on the admin log.
    USER_PASSWORD_RESET_ADMIN = "user.password_reset_admin"

    INVITE_CREATE = "invite.create"
    INVITE_REVOKE = "invite.revoke"

    @classmethod
    def all(cls) -> list[str]:
        return [
            cls.USER_APPROVE,
            cls.USER_REJECT,
            cls.USER_ROLE_CHANGE,
            cls.USER_SUSPEND,
            cls.USER_REACTIVATE,
            cls.USER_PASSWORD_RESET_ADMIN,
            cls.INVITE_CREATE,
            cls.INVITE_REVOKE,
        ]


class TargetType:
    USER = "user"
    INVITE = "invite"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log_event(
    *,
    event_type: str,
    actor_user_id_string: str,
    target_type: str,
    target_id: Optional[str] = None,
    target_label: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """
    Append a row to admin_audit_log. Swallows any exception into a
    warning — the admin endpoint's success is independent of this call.

    `actor_user_id_string` is the caller's `user_id` (email, custom
    handle, or `__local__`). We resolve it to an int FK for join-style
    queries on the read side, but if the user row is gone or solo we
    just leave the FK null and rely on the string field.
    """
    try:
        # resolve the actor's FK int if we can — defensive, not required
        actor_id_int: Optional[int] = None
        if actor_user_id_string and actor_user_id_string != DEFAULT_USER_ID:
            actor = lookup_user_by_user_id(actor_user_id_string)
            if actor is not None:
                actor_id_int = actor.id

        session = get_session()
        try:
            row = AdminAuditEvent(
                event_type=event_type,
                actor_user_id=actor_id_int,
                actor_user_id_string=actor_user_id_string or DEFAULT_USER_ID,
                target_type=target_type,
                target_id=(str(target_id) if target_id is not None else None),
                target_label=(str(target_label)[:200] if target_label is not None else None),
                audit_metadata=dict(metadata or {}),
                created_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
        finally:
            session.close()
    except Exception as e:  # noqa: BLE001 — audit must never break the action
        logger.warning(
            "audit_log: failed to write %s event by %s on %s/%s: %s",
            event_type, actor_user_id_string, target_type, target_id, e,
        )
