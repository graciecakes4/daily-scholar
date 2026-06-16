"""
Web Push (VAPID) endpoints.

Flow:
  1. Frontend hits GET /push/vapid-public-key to fetch the server's public key.
  2. Browser asks user for Notification permission.
  3. On grant, browser calls pushManager.subscribe() with that public key,
     returning a PushSubscription containing { endpoint, keys: { p256dh, auth } }.
  4. Frontend POSTs the subscription to /push/subscribe — we upsert by endpoint.
  5. Backend (push_sender.py) fans out via pywebpush when there's something to say.

All three VAPID env vars must be present for these endpoints to work. If
they're missing, every push endpoint returns 503 with a setup hint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user_id
from ..config import get_settings
from ..database import DEFAULT_USER_ID, PushSubscription, get_session

push_router = APIRouter(prefix="/push", tags=["Push"])


# ---------------------------------------------------------------------------
# pydantic schemas
# ---------------------------------------------------------------------------


class _SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    """Body of POST /push/subscribe — matches PushSubscription.toJSON()."""

    endpoint: str
    keys: _SubscriptionKeys
    platform: Optional[str] = Field(
        default=None,
        description="ios | macos | android | desktop | unknown — best-effort UA sniff from the client",
    )


class UnsubscribeRequest(BaseModel):
    endpoint: str


class TestPushRequest(BaseModel):
    title: Optional[str] = "Daily Scholar test"
    body: Optional[str] = "Push notifications are working."
    url: Optional[str] = "/"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ensure_vapid_configured() -> None:
    """Block all push endpoints if VAPID isn't set up yet."""
    s = get_settings()
    if not (s.vapid_public_key and s.vapid_private_key and s.vapid_subject):
        raise HTTPException(
            status_code=503,
            detail=(
                "Web Push not configured. Run `python scripts/generate_vapid_keys.py` "
                "and paste the output into .env, then restart the backend."
            ),
        )


def _current_user_id() -> str:
    """Kept as a function for callers that don't go through FastAPI's DI."""
    return DEFAULT_USER_ID


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@push_router.get("/vapid-public-key")
def get_vapid_public_key():
    """Return just the public key. Safe to expose; never returns the private key."""
    s = get_settings()
    if not s.vapid_public_key:
        raise HTTPException(
            status_code=503,
            detail="VAPID_PUBLIC_KEY not set. Run scripts/generate_vapid_keys.py.",
        )
    return {"public_key": s.vapid_public_key}


@push_router.post("/subscribe", status_code=201)
def subscribe(body: SubscribeRequest, user_id: str = Depends(get_current_user_id)):
    """
    Upsert a push subscription. The same endpoint URL across re-subscribes
    counts as the same physical device, so we update last_used_at instead of
    creating duplicate rows.
    """
    _ensure_vapid_configured()

    session = get_session()
    try:
        existing = session.query(PushSubscription).filter(
            PushSubscription.endpoint == body.endpoint
        ).first()
        if existing:
            existing.p256dh = body.keys.p256dh
            existing.auth = body.keys.auth
            existing.platform = body.platform or existing.platform
            existing.user_id = user_id
            existing.last_used_at = datetime.utcnow()
            session.commit()
            return {"id": existing.id, "updated": True}

        row = PushSubscription(
            user_id=user_id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            platform=body.platform or "unknown",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"id": row.id, "created": True}
    finally:
        session.close()


@push_router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeRequest):
    """Remove the subscription identified by endpoint. Idempotent."""
    session = get_session()
    try:
        row = session.query(PushSubscription).filter(
            PushSubscription.endpoint == body.endpoint
        ).first()
        if row is None:
            return {"removed": False}
        session.delete(row)
        session.commit()
        return {"removed": True}
    finally:
        session.close()


@push_router.post("/test")
def send_test(body: TestPushRequest, user_id: str = Depends(get_current_user_id)):
    """Send a sanity-check push to every subscription of the current user."""
    _ensure_vapid_configured()
    from ..services.push_sender import send_push_to_user

    payload = {
        "title": body.title or "Daily Scholar",
        "body": body.body or "Test push.",
        "url": body.url or "/",
    }
    result = send_push_to_user(user_id, payload)
    return result


@push_router.get("/subscriptions")
def list_subscriptions(user_id: str = Depends(get_current_user_id)):
    """List the current user's subscriptions (useful for debugging from the UI)."""
    session = get_session()
    try:
        rows = (
            session.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .order_by(PushSubscription.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "endpoint": r.endpoint[:60] + ("…" if len(r.endpoint) > 60 else ""),
                "platform": r.platform,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()
