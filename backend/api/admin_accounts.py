"""
Admin account-management endpoints (Phase F).

Sits alongside the existing `/admin/users` (cross-user data activity)
and `/admin/approvals` (pending-queue) routers. This one is for managing
real, post-approval User rows: list them, flip roles, suspend or
reactivate.

Notes:
  * Last-admin protection — refuse to demote or suspend the only remaining
    admin so we can't lock the system out via the UI.
  * Self-protection — refuse to suspend yourself for the same reason
    (and to avoid a "wait, why am I logged out" moment for the actor).
    Self-demotion is allowed *as long as another admin exists*.
  * Pending users go through `/admin/approvals/{id}/approve|reject`;
    this surface refuses to touch them so the two surfaces don't drift.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import lookup_user_by_user_id, require_admin
from ..database import (
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    VALID_USER_ROLES,
    VALID_USER_STATUSES,
    User,
    get_session,
)
from ..services.auth_sessions import revoke_all_sessions_for_user

logger = logging.getLogger(__name__)

admin_accounts_router = APIRouter(
    prefix="/admin/accounts",
    tags=["Admin / Accounts"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AccountSummary(BaseModel):
    """Serialized User row for the admin UI."""

    id: int
    email: str
    user_id: str
    role: str
    status: str
    onboarded: bool
    created_at: datetime
    approved_at: Optional[datetime]
    approved_by_user_id: Optional[int]
    last_login_at: Optional[datetime]


class RoleChangeBody(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


class StatusChangeBody(BaseModel):
    # only the post-approval states are settable here; pending lives
    # behind /admin/approvals
    status: str = Field(pattern="^(active|suspended)$")


def _serialize(u: User) -> AccountSummary:
    return AccountSummary(
        id=u.id,
        email=u.email,
        user_id=u.user_id,
        role=u.role,
        status=u.status,
        onboarded=getattr(u, "onboarded", True),
        created_at=u.created_at,
        approved_at=u.approved_at,
        approved_by_user_id=u.approved_by_user_id,
        last_login_at=u.last_login_at,
    )


# ---------------------------------------------------------------------------
# Internal guards
# ---------------------------------------------------------------------------


def _count_admins(session) -> int:
    """How many active admin rows exist right now."""
    return (
        session.query(User)
        .filter(User.role == USER_ROLE_ADMIN, User.status == USER_STATUS_ACTIVE)
        .count()
    )


def _resolve_actor(actor_user_id: str) -> Optional[User]:
    """The User row for the currently-acting admin. None for solo `__local__`."""
    return lookup_user_by_user_id(actor_user_id)


def _ensure_not_pending(target: User) -> None:
    """Both endpoints refuse to operate on pending users."""
    if target.status == USER_STATUS_PENDING:
        raise HTTPException(
            status_code=400,
            detail=(
                "This user is pending approval. Use /admin/approvals to approve "
                "or reject them instead of editing their account directly."
            ),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@admin_accounts_router.get("", response_model=list[AccountSummary])
def list_accounts(
    status: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
):
    """
    List every User row, newest-first, with optional status/role filters.

    Pending users show up here too so admins can see the queue + the
    rest of the population in one place — but mutations on them are
    refused (use the dedicated approvals endpoints).
    """
    if status is not None and status not in VALID_USER_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")
    if role is not None and role not in VALID_USER_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role: {role}")

    session = get_session()
    try:
        q = session.query(User).order_by(User.created_at.desc())
        if status is not None:
            q = q.filter(User.status == status)
        if role is not None:
            q = q.filter(User.role == role)
        return [_serialize(u) for u in q.all()]
    finally:
        session.close()


@admin_accounts_router.put("/{target_user_id}/role", response_model=AccountSummary)
def change_role(
    target_user_id: str,
    body: RoleChangeBody,
    actor_user_id: str = Depends(require_admin),
):
    """
    Promote a user to admin, or demote an admin back to user.

    Last-admin protection: if the change would leave zero active admins,
    refuse. Self-demotion is allowed as long as another admin exists
    (you might rotate ownership), but be wary — you can't un-demote
    yourself after.
    """
    session = get_session()
    try:
        target = session.query(User).filter(User.user_id == target_user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        _ensure_not_pending(target)

        if target.role == body.role:
            # idempotent: return current state without churning the row
            return _serialize(target)

        # last-admin protection: a demotion that drops admin count to 0
        # is refused. Check BEFORE applying.
        if body.role == USER_ROLE_USER and target.role == USER_ROLE_ADMIN:
            remaining_admins = _count_admins(session)
            if remaining_admins <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote the last remaining admin.",
                )

        target.role = body.role
        session.commit()
        session.refresh(target)
        return _serialize(target)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("change_role: %s", e)
        raise HTTPException(status_code=500, detail="Could not change role")
    finally:
        session.close()


@admin_accounts_router.put("/{target_user_id}/status", response_model=AccountSummary)
def change_status(
    target_user_id: str,
    body: StatusChangeBody,
    actor_user_id: str = Depends(require_admin),
):
    """
    Suspend or reactivate a user.

    On suspend:
      * revoke every active session for the target so they're kicked
        out of any open tabs immediately (next request → 403)
      * refuse if the target is the actor (no self-lockout)
      * refuse if the target is the last admin (same lockout risk as
        change_role)
    On reactivate (suspended → active): just flip the flag; sessions
    they had are already revoked and won't auto-restore.
    """
    actor = _resolve_actor(actor_user_id)

    session = get_session()
    try:
        target = session.query(User).filter(User.user_id == target_user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        _ensure_not_pending(target)

        if target.status == body.status:
            return _serialize(target)

        if body.status == USER_STATUS_SUSPENDED:
            # self-suspend
            if actor is not None and actor.id == target.id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot suspend yourself.",
                )
            # last-admin check
            if target.role == USER_ROLE_ADMIN:
                remaining_admins = _count_admins(session)
                if remaining_admins <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot suspend the last remaining admin.",
                    )

        target.status = body.status
        session.commit()

        # do the session revocation OUTSIDE the user-update transaction
        # so a session-revoke error doesn't roll back the status flip
        target_id = target.id
        session.refresh(target)
        result = _serialize(target)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("change_status: %s", e)
        raise HTTPException(status_code=500, detail="Could not change status")
    finally:
        session.close()

    if body.status == USER_STATUS_SUSPENDED:
        try:
            revoke_all_sessions_for_user(target_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("change_status: session revoke failed for user %s: %s", target_id, e)

    return result
