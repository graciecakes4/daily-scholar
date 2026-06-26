"""
Admin endpoints for invite-code management.

Admin generates codes here; hands them out (text/email/Slack/etc); the
user types them at signup; the signup endpoint atomically validates +
redeems via the same `validate_and_redeem` call this module's CRUD
operations live alongside.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import lookup_user_by_user_id, require_admin
from ..database import DEFAULT_USER_ID
from ..services.invite_codes import (
    generate_invite_code,
    list_invite_codes,
    revoke_invite_code,
)

logger = logging.getLogger(__name__)

admin_invites_router = APIRouter(
    prefix="/admin/invites",
    tags=["Admin / Invites"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateInviteBody(BaseModel):
    """POST /admin/invites — generate a new code."""

    # null = no expiry; otherwise an integer number of days from now
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Days until expiry (1-365). Omit for a non-expiring code.",
    )
    max_uses: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="How many signups can redeem this code (default 1 = single-use).",
    )


class InviteSummary(BaseModel):
    """Shape returned by list / create. Hides nothing sensitive — the
    code itself is the secret, and we're returning it to its creator."""

    id: int
    code: str
    created_at: datetime
    expires_at: Optional[datetime]
    max_uses: int
    uses: int
    redeemed_at: Optional[datetime]
    revoked_at: Optional[datetime]
    # convenience flag — UI uses this for color/status
    state: str  # "available" | "exhausted" | "expired" | "revoked"


def _state_of(row) -> str:
    """Compute the UI-friendly state label from the row's fields."""
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at is not None and row.expires_at <= datetime.utcnow():
        return "expired"
    if row.uses >= row.max_uses:
        return "exhausted"
    return "available"


def _summarize(row) -> InviteSummary:
    return InviteSummary(
        id=row.id,
        code=row.code,
        created_at=row.created_at,
        expires_at=row.expires_at,
        max_uses=row.max_uses,
        uses=row.uses,
        redeemed_at=row.redeemed_at,
        revoked_at=row.revoked_at,
        state=_state_of(row),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@admin_invites_router.get("")
def list_invites(
    include_revoked: bool = True,
    _: str = Depends(require_admin),
) -> dict:
    rows = list_invite_codes(include_revoked=include_revoked)
    return {"invites": [_summarize(r).model_dump() for r in rows]}


@admin_invites_router.post("", status_code=201)
def create_invite(
    body: CreateInviteBody,
    user_id: str = Depends(require_admin),
) -> dict:
    """
    Generate one invite code. Returned `code` is the value to share with
    the recipient.

    Solo dev (__local__) doesn't have a real User row, so we use a
    dedicated sentinel admin's id. In practice solo never hits this
    endpoint because there's nobody to invite — but it shouldn't 500
    if you poke it.
    """
    # resolve the admin's user.id for the FK. __local__ has no User row;
    # fall back to a sentinel value (0) so the FK column is satisfied.
    # The endpoint is admin-gated already, so this is purely for the
    # foreign-key insert to succeed in solo dev.
    if user_id == DEFAULT_USER_ID:
        # solo dev shortcut — no User row exists for __local__
        raise HTTPException(
            status_code=400,
            detail="Cannot create invites in solo mode — there are no other users to invite. "
                   "Set up an in-app admin account first with scripts/create_admin.py.",
        )

    admin_user = lookup_user_by_user_id(user_id)
    if admin_user is None:
        # require_admin already gated this, but defensive
        raise HTTPException(status_code=500, detail="Admin user record missing")

    expires_at: Optional[datetime] = None
    if body.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)

    row = generate_invite_code(
        created_by_user_id=admin_user.id,
        expires_at=expires_at,
        max_uses=body.max_uses,
    )
    return {"invite": _summarize(row).model_dump()}


@admin_invites_router.delete("/{invite_id}")
def revoke_invite(invite_id: int, _: str = Depends(require_admin)) -> dict:
    """
    Mark an invite code revoked. Idempotent.
    """
    revoked = revoke_invite_code(invite_id)
    if not revoked:
        # could be already-revoked or unknown id — return same shape either
        # way so the UI can refresh without branching
        return {"ok": True, "revoked": False}
    return {"ok": True, "revoked": True}
