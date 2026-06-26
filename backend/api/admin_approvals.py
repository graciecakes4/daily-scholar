"""
Admin endpoints for the user approval queue.

New signups land in `users.status='pending'` (Phase A). An admin uses
this surface to flip them to `active` (approval) or remove the row
entirely (rejection). Approve stamps `approved_at` + `approved_by_user_id`
for audit; reject deletes the user row + any sessions / settings rows
the user may have created during their "pending login" window.

Future Phase F: a 'rejected' graveyard status with rationale + appeal
flow. For now reject = delete, which is the simplest thing that's safe
(rejected users can sign up again with a fresh invite if you choose to
give them one).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import lookup_user_by_user_id, require_admin
from ..database import (
    DEFAULT_USER_ID,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    User,
    UserSettings,
    UserStats,
    get_session,
)
from ..services.audit_log import EventType, TargetType, log_event
from ..services.auth_sessions import revoke_all_sessions_for_user

logger = logging.getLogger(__name__)

admin_approvals_router = APIRouter(
    prefix="/admin/approvals",
    tags=["Admin / Approvals"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PendingUserSummary(BaseModel):
    id: int
    email: str
    user_id: str
    created_at: datetime
    # convenience: how long they've been waiting, for the UI to render
    waiting_seconds: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@admin_approvals_router.get("")
def list_pending(_: str = Depends(require_admin)) -> dict:
    """
    All `pending` users, oldest first (longest waiting → top of queue).
    """
    session = get_session()
    try:
        rows = (
            session.query(User)
            .filter(User.status == USER_STATUS_PENDING)
            .order_by(User.created_at.asc())
            .all()
        )
        now = datetime.utcnow()
        items = [
            PendingUserSummary(
                id=u.id,
                email=u.email,
                user_id=u.user_id,
                created_at=u.created_at,
                waiting_seconds=int((now - u.created_at).total_seconds()),
            ).model_dump()
            for u in rows
        ]
        return {"pending": items, "count": len(items)}
    finally:
        session.close()


def _resolve_approving_admin_id(actor_user_id: str) -> Optional[int]:
    """
    Translate the admin's `user_id` string into the integer id we stamp on
    `users.approved_by_user_id`. Returns None for solo `__local__` so the
    column stays NULL (consistent with the bootstrap admin who also has
    nobody to approve them).
    """
    if actor_user_id == DEFAULT_USER_ID:
        return None
    actor = lookup_user_by_user_id(actor_user_id)
    return actor.id if actor is not None else None


@admin_approvals_router.post("/{pending_user_id}/approve")
def approve(
    pending_user_id: int,
    actor_user_id: str = Depends(require_admin),
) -> dict:
    """
    Flip a pending user to active and stamp the approval audit fields.
    Idempotent: approving an already-active user is a no-op success.
    """
    session = get_session()
    try:
        target = session.query(User).filter(User.id == pending_user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")

        if target.status == USER_STATUS_ACTIVE:
            return {"ok": True, "message": "User is already active"}

        if target.status != USER_STATUS_PENDING:
            # suspended / unknown status → don't silently approve; the admin
            # should explicitly unsuspend via a separate endpoint (Phase F)
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve from status '{target.status}'",
            )

        target.status = USER_STATUS_ACTIVE
        target.approved_at = datetime.utcnow()
        target.approved_by_user_id = _resolve_approving_admin_id(actor_user_id)
        # snapshot fields before closing the session so we can log + return
        # without touching a detached row
        target_user_id_str = target.user_id
        target_email = target.email
        approved_at_iso = target.approved_at.isoformat()
        session.commit()
    finally:
        session.close()

    log_event(
        event_type=EventType.USER_APPROVE,
        actor_user_id_string=actor_user_id,
        target_type=TargetType.USER,
        target_id=target_user_id_str,
        target_label=target_email,
        metadata={"approved_at": approved_at_iso},
    )

    return {
        "ok": True,
        "user_id": target_user_id_str,
        "email": target_email,
        "approved_at": approved_at_iso,
    }


@admin_approvals_router.post("/{pending_user_id}/reject")
def reject(
    pending_user_id: int,
    actor_user_id: str = Depends(require_admin),
) -> dict:
    """
    Delete the pending user (and any rows they created during their
    "pending login" window: sessions, settings, stats). Refuses to delete
    an `active` user — that's a separate "delete account" operation we
    haven't built yet.
    """
    session = get_session()
    try:
        target = session.query(User).filter(User.id == pending_user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")

        if target.status != USER_STATUS_PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Refusing to reject a '{target.status}' user via this endpoint",
            )

        # revoke any sessions the pending user created while logged in
        revoke_all_sessions_for_user(target.id)

        # delete the tiny set of rows a pending user can have created.
        # archived_* are unlikely (pending users get 403 on those endpoints
        # via get_current_user_id), but settings/stats can be auto-created
        # by lazy-init helpers — wipe them so a re-signup gets a clean slate.
        target_uid = target.user_id
        target_email = target.email
        for model in (UserSettings, UserStats):
            session.query(model).filter(model.user_id == target_uid).delete(
                synchronize_session=False
            )

        session.delete(target)
        session.commit()
    finally:
        session.close()

    log_event(
        event_type=EventType.USER_REJECT,
        actor_user_id_string=actor_user_id,
        target_type=TargetType.USER,
        target_id=target_uid,
        target_label=target_email,
        metadata={"deleted": True},
    )

    return {"ok": True, "deleted_user_id": target_uid}
