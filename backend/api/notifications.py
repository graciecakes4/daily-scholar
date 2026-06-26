"""
Notification configuration + manual-trigger endpoints.

Read/write the per-user notification_settings blob, list the registry of
available types, preview a payload without sending it (for the UI), and
fire one notification on-demand (Test button).

Every mutating endpoint re-syncs APScheduler jobs for the user so toggling
a notification on/off takes effect immediately — no restart required.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user_id
from ..services import notifications as notif

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# pydantic schemas
# ---------------------------------------------------------------------------


class NotificationTypeEntry(BaseModel):
    """One per-type setting block in the user's preferences."""

    enabled: bool = False
    # standard 5-field cron: "M H D Mo DOW"
    cron: str = Field(
        default="0 9 * * *",
        description="Standard 5-field cron expression (M H D Mo DOW), evaluated in `timezone`.",
    )


class NotificationSettingsBody(BaseModel):
    """Full user prefs blob — sent on every PUT (no PATCH semantics)."""

    timezone: str = Field(
        default="America/New_York",
        description="IANA timezone name used for every cron trigger.",
    )
    # keyed by registry type_key
    types: dict[str, NotificationTypeEntry] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@notifications_router.get("/types")
def list_notification_types() -> dict[str, Any]:
    """
    Registry of available notification types. Drives the settings UI —
    one card per entry. Stable list across deploys; new types appear here
    the moment they're added to notifications.REGISTRY.
    """
    return {"types": notif.list_types()}


@notifications_router.get("/settings")
def get_settings(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    """
    Current notification preferences for the calling user. Always returns
    a fully-populated blob — missing type entries are backfilled from the
    registry defaults so the UI can render every card without conditional
    fallbacks.
    """
    return notif.get_notification_settings(user_id)


@notifications_router.put("/settings")
def update_settings(
    body: NotificationSettingsBody,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Replace this user's notification preferences. Triggers an immediate
    APScheduler reload so freshly-enabled jobs fire on their next cron
    tick and disabled ones stop sending right away.
    """
    from ..services.scheduler import reload_notification_jobs_for_user

    # convert pydantic dict-of-models into a plain dict for the service layer
    payload = {
        "timezone": body.timezone,
        "types": {k: v.model_dump() for k, v in body.types.items()},
    }
    normalized = notif.update_notification_settings(user_id, payload)
    reload_result = reload_notification_jobs_for_user(user_id)
    return {"settings": normalized, "scheduler": reload_result}


@notifications_router.get("/preview/{type_key}")
async def preview_notification(
    type_key: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Build the payload for `type_key` and return it without sending. Useful
    so the settings UI can show 'this is what your weekly recap looks like
    right now' next to the toggle.
    """
    if type_key not in notif.REGISTRY:
        raise HTTPException(status_code=404, detail=f"unknown notification type: {type_key}")

    try:
        payload = await notif.build_payload(user_id, type_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"builder failed: {e}")

    return {
        "type": type_key,
        "payload": payload,                       # may be None — UI shows "nothing to send"
        "would_send": payload is not None,
    }


@notifications_router.post("/test/{type_key}")
async def send_test_notification(
    type_key: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Fire one notification immediately. Goes through the same dispatch
    code path as scheduled sends so a green Test button means scheduled
    delivery will also work.
    """
    if type_key not in notif.REGISTRY:
        raise HTTPException(status_code=404, detail=f"unknown notification type: {type_key}")

    result = await notif.dispatch_notification(user_id, type_key)
    return result


@notifications_router.get("/jobs")
def list_user_notification_jobs(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Inspect this user's currently-scheduled notification jobs. Lets the
    UI confirm a saved setting actually became a live cron trigger
    (catches things like a typo'd cron that the loader skipped).
    """
    from ..services.scheduler import _notif_job_id, get_scheduler

    sched = get_scheduler()
    if sched is None:
        return {"scheduler_running": False, "jobs": []}

    jobs: list[dict[str, Optional[str]]] = []
    for type_key in notif.REGISTRY:
        job = sched.get_job(_notif_job_id(user_id, type_key))
        if job is None:
            continue
        jobs.append({
            "type": type_key,
            "id": job.id,
            "trigger": str(job.trigger),
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {"scheduler_running": True, "jobs": jobs}
