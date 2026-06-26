"""
APScheduler wiring for background jobs.

Started/stopped by the FastAPI lifespan handler. Two job classes today:

  nightly-daily-content
      cron at DAILY_GENERATION_TIME in TIMEZONE — regenerates that day's
      daily_content for DEFAULT_USER_ID and auto-fires Web Push on a new
      paper. Static across deploys.

  notif:<user_id>:<type_key>
      dynamic — one job per (user, enabled notification type). Created
      from each user's UserSettings.notification_settings JSON via
      reload_notification_jobs_for_user(). Re-runs after the
      /notifications/settings endpoint mutates that user's prefs.

Disabled when SCHEDULER_DISABLED env var is set ("1"/"true") — useful
for tests and CI where you don't want background work running.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover — apscheduler is in requirements
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]

from ..config import get_settings
from ..database import DEFAULT_USER_ID, UserSettings, get_session

logger = logging.getLogger(__name__)

_scheduler: Optional["AsyncIOScheduler"] = None


def _is_disabled() -> bool:
    val = os.environ.get("SCHEDULER_DISABLED", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def get_scheduler() -> Optional["AsyncIOScheduler"]:
    """Expose the global scheduler so endpoints / admin routes can poke at it."""
    return _scheduler


# ---------------------------------------------------------------------------
# Static job: nightly daily-content generation
# ---------------------------------------------------------------------------


async def _run_daily_generation() -> None:
    """Job target: regenerate today's content from scratch for the local user."""
    from .daily_content import generate_daily_content

    logger.info("scheduler: starting nightly daily-content generation")
    try:
        result = await generate_daily_content(
            refresh="all",
            user_id=DEFAULT_USER_ID,
            fire_push_on_new_paper=True,
        )
        paper = (result or {}).get("paper") or {}
        title = paper.get("title", "<no paper>") if isinstance(paper, dict) else "<no paper>"
        logger.info("scheduler: nightly daily-content done — paper=%r", title[:60])
    except Exception as e:  # noqa: BLE001 — never let a job kill the scheduler
        logger.exception("scheduler: nightly daily-content failed: %s", e)


# ---------------------------------------------------------------------------
# Dynamic jobs: per-user notifications
# ---------------------------------------------------------------------------


def _notif_job_id(user_id: str, type_key: str) -> str:
    """Stable id for a single user's notification job. Used for replace/remove."""
    # `:` is a safe separator — APScheduler treats job_id as opaque.
    return f"notif:{user_id}:{type_key}"


async def _run_notification(user_id: str, type_key: str) -> None:
    """Job target: build + send one notification for one user."""
    from .notifications import dispatch_notification

    logger.info("scheduler: running notification %s for %s", type_key, user_id)
    try:
        await dispatch_notification(user_id, type_key)
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "scheduler: notification %s for %s failed: %s",
            type_key, user_id, e,
        )


def _add_notification_job(
    sched: "AsyncIOScheduler",
    user_id: str,
    type_key: str,
    cron: str,
    timezone: str,
) -> None:
    """
    Register one notification job. Idempotent: replaces an existing job
    with the same id (so updating cron via the settings endpoint just
    re-registers the trigger).
    """
    if CronTrigger is None:  # pragma: no cover
        return
    try:
        trigger = CronTrigger.from_crontab(cron, timezone=timezone)
    except (ValueError, TypeError) as e:
        # bad cron in settings — log + skip, don't blow up the whole reload
        logger.warning(
            "scheduler: bad cron %r for %s/%s: %s — skipping",
            cron, user_id, type_key, e,
        )
        return

    job_id = _notif_job_id(user_id, type_key)
    sched.add_job(
        _run_notification,
        trigger=trigger,
        args=(user_id, type_key),
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "scheduler: registered %s (cron=%r tz=%s)", job_id, cron, timezone
    )


def _remove_notification_job(sched: "AsyncIOScheduler", user_id: str, type_key: str) -> None:
    """Drop a notification job if present; silent no-op if it isn't."""
    job_id = _notif_job_id(user_id, type_key)
    if sched.get_job(job_id) is not None:
        sched.remove_job(job_id)
        logger.info("scheduler: removed %s", job_id)


def reload_notification_jobs_for_user(user_id: str) -> dict[str, int]:
    """
    Sync APScheduler's job set with this user's notification_settings.

    For each registry type:
      - if enabled in settings → add_job (replace_existing handles updates)
      - if not enabled → remove_job (idempotent)

    Returns counts dict for the calling endpoint to surface.
    """
    if _scheduler is None:
        # scheduler disabled (CI/tests) or not yet started — silent no-op.
        return {"added": 0, "removed": 0, "skipped_scheduler_disabled": 1}

    from .notifications import REGISTRY, get_notification_settings

    settings_blob = get_notification_settings(user_id)
    tz = settings_blob.get("timezone") or "UTC"
    types = settings_blob.get("types") or {}

    added = removed = 0
    for type_key in REGISTRY:
        entry = types.get(type_key) or {}
        if entry.get("enabled"):
            _add_notification_job(
                _scheduler, user_id, type_key, entry.get("cron", ""), tz
            )
            added += 1
        else:
            before = _scheduler.get_job(_notif_job_id(user_id, type_key))
            _remove_notification_job(_scheduler, user_id, type_key)
            if before is not None:
                removed += 1
    return {"added": added, "removed": removed}


def reload_all_notification_jobs() -> dict[str, int]:
    """
    Sweep every UserSettings row and reload its notification jobs.
    Called once at startup so jobs persist across restarts.
    """
    if _scheduler is None:
        return {"users": 0, "added": 0, "removed": 0, "skipped_scheduler_disabled": 1}

    session = get_session()
    try:
        user_ids = [u.user_id for u in session.query(UserSettings).all()]
    finally:
        session.close()

    added = removed = 0
    for uid in user_ids:
        result = reload_notification_jobs_for_user(uid)
        added += result.get("added", 0)
        removed += result.get("removed", 0)
    return {"users": len(user_ids), "added": added, "removed": removed}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_scheduler() -> Optional["AsyncIOScheduler"]:
    """Construct and start the global scheduler. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if _is_disabled():
        logger.info("scheduler: disabled via SCHEDULER_DISABLED env var")
        return None
    if AsyncIOScheduler is None:
        logger.warning("scheduler: apscheduler not installed; skipping")
        return None

    settings = get_settings()
    sched = AsyncIOScheduler(timezone=settings.timezone or "UTC")

    # parse HH:MM
    raw = (settings.daily_generation_time or "06:00").strip()
    try:
        hour_str, minute_str = raw.split(":", 1)
        hour, minute = int(hour_str), int(minute_str)
    except (ValueError, AttributeError):
        logger.warning(
            "scheduler: bad DAILY_GENERATION_TIME=%r, falling back to 06:00", raw
        )
        hour, minute = 6, 0

    sched.add_job(
        _run_daily_generation,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="nightly-daily-content",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    logger.info(
        "scheduler: started; nightly-daily-content at %02d:%02d %s",
        hour, minute, settings.timezone,
    )
    _scheduler = sched

    # boot per-user notification jobs from settings JSON
    try:
        summary = reload_all_notification_jobs()
        logger.info(
            "scheduler: notification jobs reloaded — users=%d added=%d removed=%d",
            summary.get("users", 0),
            summary.get("added", 0),
            summary.get("removed", 0),
        )
    except Exception as e:  # noqa: BLE001 — never let user-settings bugs break boot
        logger.exception("scheduler: notification reload at boot failed: %s", e)

    return sched


def stop_scheduler() -> None:
    """Stop the global scheduler if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")
        _scheduler = None


def list_jobs() -> list[dict]:
    """Return the active job list for debugging via the admin endpoint."""
    if _scheduler is None:
        return []
    return [
        {
            "id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in _scheduler.get_jobs()
    ]


async def trigger_now(job_id: str = "nightly-daily-content") -> dict:
    """Manually fire a scheduled job. Useful for admin/debugging."""
    if _scheduler is None:
        return {"ok": False, "error": "scheduler not running"}
    job = _scheduler.get_job(job_id)
    if job is None:
        return {"ok": False, "error": f"no job named {job_id!r}"}
    # jobs may be sync or async; await if needed
    import inspect
    result = job.func(*(job.args or ()), **(job.kwargs or {}))
    if inspect.isawaitable(result):
        await result
    return {"ok": True, "ran": job_id}
