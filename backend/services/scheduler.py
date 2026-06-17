"""
APScheduler wiring for background jobs.

Started/stopped by the FastAPI lifespan handler. Currently runs one job:

    nightly-daily-content   cron at DAILY_GENERATION_TIME in TIMEZONE
        -> generate_daily_content(refresh="all") for the local user
           (auto-fires Web Push when a fresh paper is found)

Disabled when the SCHEDULER_DISABLED env var is set ("1"/"true") — useful
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
from ..database import DEFAULT_USER_ID

logger = logging.getLogger(__name__)

_scheduler: Optional["AsyncIOScheduler"] = None


def _is_disabled() -> bool:
    val = os.environ.get("SCHEDULER_DISABLED", "").strip().lower()
    return val in ("1", "true", "yes", "on")


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
    await job.func()
    return {"ok": True, "ran": job_id}
