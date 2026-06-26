"""
GET /admin/audit — read endpoint for the admin audit log.

Append-only; nothing in this module writes. Writes happen via
`services/audit_log.log_event` from inside the mutation endpoints.

Filters (all optional): event_type, actor (matches the denormalized
actor_user_id_string), target_id, since/until (ISO datetime strings).
Pagination via limit + offset (newest first).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_admin
from ..database import AdminAuditEvent, get_session
from ..services.audit_log import EventType

admin_audit_router = APIRouter(
    prefix="/admin/audit",
    tags=["Admin / Audit"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    id: int
    event_type: str
    actor_user_id: Optional[int]
    actor_user_id_string: str
    target_type: str
    target_id: Optional[str]
    target_label: Optional[str]
    metadata: dict[str, Any]
    created_at: datetime


def _serialize(row: AdminAuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=row.id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        actor_user_id_string=row.actor_user_id_string,
        target_type=row.target_type,
        target_id=row.target_id,
        target_label=row.target_label,
        metadata=dict(row.audit_metadata or {}),
        created_at=row.created_at,
    )


def _parse_dt(value: Optional[str], field: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        # accept both "2026-06-26" and full ISO; fromisoformat handles both
        # ("2026-06-26" → midnight UTC date)
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"invalid datetime for {field}: {value}",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@admin_audit_router.get("")
def list_events(
    event_type: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(
        default=None,
        description="Match against actor_user_id_string (email or handle).",
    ),
    target_id: Optional[str] = Query(default=None),
    since: Optional[str] = Query(
        default=None,
        description="ISO datetime; events with created_at >= since.",
    ),
    until: Optional[str] = Query(
        default=None,
        description="ISO datetime; events with created_at <= until.",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if event_type is not None and event_type not in EventType.all():
        raise HTTPException(
            status_code=400,
            detail=f"unknown event_type: {event_type}",
        )

    since_dt = _parse_dt(since, "since")
    until_dt = _parse_dt(until, "until")

    session = get_session()
    try:
        q = session.query(AdminAuditEvent)
        if event_type is not None:
            q = q.filter(AdminAuditEvent.event_type == event_type)
        if actor is not None:
            q = q.filter(AdminAuditEvent.actor_user_id_string == actor)
        if target_id is not None:
            q = q.filter(AdminAuditEvent.target_id == target_id)
        if since_dt is not None:
            q = q.filter(AdminAuditEvent.created_at >= since_dt)
        if until_dt is not None:
            q = q.filter(AdminAuditEvent.created_at <= until_dt)

        total = q.count()
        rows = (
            q.order_by(AdminAuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "events": [_serialize(r).model_dump() for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        session.close()


@admin_audit_router.get("/event-types")
def list_event_types() -> dict:
    """The closed set of event_type strings the UI filter dropdown uses."""
    return {"event_types": EventType.all()}
