"""
Notification builders + per-user settings store.

This module owns three things:

  1. The *registry* of notification types. Each entry is a stable key,
     a human label, a sensible default cron, and an async `build()` that
     returns the push payload (or None to skip the send).

  2. The settings helpers: load / merge / save the per-user
     `UserSettings.notification_settings` JSON blob, with safe defaults
     and migration-on-read so adding a new type to the registry doesn't
     leave existing users with a missing key.

  3. The runtime dispatch: `dispatch_notification(user_id, type_key)` —
     builds the payload, fans it out via push_sender. Used by both the
     scheduler jobs and the /notifications/test/{type} endpoint.

Adding a new type is a registry entry + (optionally) a default cron;
no DB migration, no UI hardcoding. The settings page renders one card
per registry entry.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.orm import Session

from ..database import (
    DEFAULT_USER_ID,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    DailyContentCache,
    SeenPaper,
    Topic,
    UserSettings,
    UserStats,
    get_or_create_user_settings,
    get_session,
    get_topics_for_scope,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry types
# ---------------------------------------------------------------------------


# A notification payload. Mirrors what the service worker expects in its
# 'push' event handler — see PushSubscription.toJSON() on the frontend side.
PushPayload = dict[str, Any]


# Builder signature: an async function that returns a push payload or None
# (None means "skip the send" — e.g., nothing to remind about today).
Builder = Callable[[str], Awaitable[Optional[PushPayload]]]


@dataclass(frozen=True)
class NotificationType:
    """One entry in the registry."""

    key: str                       # stable id; used in settings JSON + URLs
    label: str                     # human-facing label for the settings UI
    description: str               # one-line help text
    default_cron: str              # 5-field cron used when user first enables
    builder: Builder               # callable that produces the payload


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


# Settings JSON shape (per user). Kept tiny and forward-compatible.
DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "timezone": "America/New_York",
    "types": {},  # filled by ensure_settings_shape() from the registry
}


def _registry_defaults() -> dict[str, dict[str, Any]]:
    """Build a fresh per-type defaults dict from the live registry."""
    return {
        nt.key: {"enabled": False, "cron": nt.default_cron}
        for nt in REGISTRY.values()
    }


def ensure_settings_shape(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Normalize a stored notification_settings blob.

    Tolerates None / partial blobs / blobs from older registry versions, and
    backfills any missing type entries from current defaults. Pure — does
    not write back to the DB; callers do that themselves if they care.
    """
    raw = dict(raw or {})
    tz = raw.get("timezone") or DEFAULT_NOTIFICATION_SETTINGS["timezone"]

    types_in = dict(raw.get("types") or {})
    types_out: dict[str, dict[str, Any]] = {}
    defaults = _registry_defaults()
    for key, default in defaults.items():
        entry = dict(types_in.get(key) or {})
        entry.setdefault("enabled", bool(default["enabled"]))
        entry.setdefault("cron", default["cron"])
        # belt-and-braces: clamp enabled to a real bool, cron to a str
        entry["enabled"] = bool(entry["enabled"])
        entry["cron"] = str(entry["cron"])
        types_out[key] = entry

    return {"timezone": str(tz), "types": types_out}


def get_notification_settings(user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """Read + normalize the settings blob for `user_id`."""
    settings = get_or_create_user_settings(user_id)
    return ensure_settings_shape(settings.notification_settings)


def update_notification_settings(
    user_id: str, new_settings: dict[str, Any]
) -> dict[str, Any]:
    """
    Replace the user's notification settings (normalized) and persist.
    Returns the normalized blob.
    """
    normalized = ensure_settings_shape(new_settings)
    session = get_session()
    try:
        settings = (
            session.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )
        if settings is None:
            settings = UserSettings(user_id=user_id, scope_mode="all", scope_topic_ids=[])
            session.add(settings)
            session.flush()
        settings.notification_settings = normalized
        settings.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()
    return normalized


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip(text: Optional[str], limit: int = 140) -> str:
    """Trim a string for push-body length; tolerates None."""
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _load_cached_daily(user_id: str, on_date: Optional[date] = None) -> Optional[DailyContentCache]:
    """Return today's (or `on_date`'s) DailyContentCache row, if any."""
    on_date = on_date or date.today()
    session = get_session()
    try:
        return (
            session.query(DailyContentCache)
            .filter(
                DailyContentCache.user_id == user_id,
                DailyContentCache.content_date == on_date,
            )
            .first()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


async def build_study_reminder(user_id: str) -> Optional[PushPayload]:
    """
    Smart study nudge — pulls today's queued topic/paper out of the
    daily-content cache so the notification body reflects what the user
    will actually see when they open the app. Falls back to a plain
    nudge if nothing's cached yet.
    """
    cached = _load_cached_daily(user_id)
    topic_name: Optional[str] = None
    paper_title: Optional[str] = None

    if cached:
        # topic_reviews shape: [{"topic": {...}, "review": {...}}, ...]
        reviews = cached.topic_reviews or []
        if reviews and isinstance(reviews, list):
            first = reviews[0] if isinstance(reviews[0], dict) else {}
            topic = first.get("topic") or {}
            topic_name = topic.get("name")
        paper = cached.paper_data or {}
        if isinstance(paper, dict):
            paper_title = paper.get("title")

    if topic_name and paper_title:
        body = f"Today's topic: {topic_name}. Paper: {_strip(paper_title, 80)}"
    elif topic_name:
        body = f"Today's topic: {topic_name}"
    elif paper_title:
        body = f"Today's paper: {_strip(paper_title, 120)}"
    else:
        body = "Open Daily Scholar to get today's paper and topic review."

    return {
        "title": "Time to study",
        "body": body,
        "url": "/",
        "tag": "study-reminder",
    }


async def build_paper_drop(user_id: str) -> Optional[PushPayload]:
    """
    Push a single fresh paper. Pulls one unseen, in-scope paper via the
    same discovery service the daily endpoint uses; if discovery finds
    nothing (rare — usually a slow upstream), returns None so we don't
    spam an empty notification.
    """
    from ..database import get_seen_paper_ids, mark_paper_as_seen
    from .paper_discovery import PaperDiscoveryService

    seen_ids = list(get_seen_paper_ids(user_id=user_id))
    service = PaperDiscoveryService(user_id=user_id)
    try:
        paper = await service.select_daily_paper(seen_ids=seen_ids, days_back=30)
    finally:
        await service.close()

    if paper is None:
        logger.info("paper_drop: no fresh paper for %s", user_id)
        return None

    paper_dict = paper.to_dict()
    paper_dict["unique_id"] = paper.unique_id
    # mark seen so the nightly job + UI don't show it again
    mark_paper_as_seen(paper_dict, user_id=user_id)

    return {
        "title": "New paper for you",
        "body": _strip(paper.title, 140),
        # deep-link to the paper page; falls back to the home discovery view
        "url": f"/papers/discover?focus={paper.unique_id}",
        "tag": "paper-drop",
        "data": {"unique_id": paper.unique_id, "source": paper.source},
    }


# weekly status helpers ------------------------------------------------------


def _activity_for_topic_last_week(
    session: Session, user_id: str, topic_id: str, since: datetime
) -> tuple[int, int]:
    """
    Count (papers_linked, reviews) for one topic since `since`.

    linked_topic_ids on ArchivedPaper is a JSON list; we filter post-load
    rather than building a JSON-contains expression that's dialect-sensitive
    between SQLite and Postgres.
    """
    paper_count = 0
    papers = (
        session.query(ArchivedPaper.linked_topic_ids)
        .filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.archived_at >= since,
        )
        .all()
    )
    for (links,) in papers:
        if isinstance(links, list) and topic_id in links:
            paper_count += 1

    review_count = (
        session.query(ArchivedTopicReview)
        .filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.topic_id == topic_id,
            ArchivedTopicReview.last_reviewed_at >= since,
        )
        .count()
    )
    return paper_count, review_count


def _compute_weekly_blind_spot(user_id: str, since: datetime) -> Optional[str]:
    """
    Return the name of one in-scope, not-completed topic that had ZERO
    paper-archive or review activity in the last week. The 'lowest weight,
    fewest historical reviews' tiebreak biases toward topics that have
    been chronically neglected, not just quiet-this-week ones.
    """
    scope = get_topics_for_scope(user_id=user_id)
    if not scope:
        return None

    session = get_session()
    try:
        candidates: list[tuple[Topic, int]] = []
        for topic in scope:
            papers, reviews = _activity_for_topic_last_week(
                session, user_id, topic.id, since
            )
            if papers == 0 and reviews == 0:
                # lifetime review count as the staleness tiebreaker
                lifetime_reviews = (
                    session.query(ArchivedTopicReview)
                    .filter(
                        ArchivedTopicReview.user_id == user_id,
                        ArchivedTopicReview.topic_id == topic.id,
                    )
                    .count()
                )
                candidates.append((topic, lifetime_reviews))
        if not candidates:
            return None
        # smallest lifetime-review count wins (most neglected)
        candidates.sort(key=lambda x: (x[1], x[0].weight, x[0].name))
        return candidates[0][0].name
    finally:
        session.close()


async def build_weekly_status(user_id: str) -> Optional[PushPayload]:
    """
    Weekly recap. Body packs: streak, papers seen this week, topic
    coverage count, top paper of the week, and a blind-spot suggestion.
    Per Grace's spec — no LLM call; this is a pure SQL roll-up so the
    weekly job is cheap and deterministic.
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    session = get_session()
    try:
        stats = (
            session.query(UserStats)
            .filter(UserStats.user_id == user_id)
            .first()
        )
        streak = stats.current_streak_days if stats else 0

        papers_seen_week = (
            session.query(SeenPaper)
            .filter(
                SeenPaper.user_id == user_id,
                SeenPaper.shown_at >= week_ago,
            )
            .count()
        )

        # topic coverage: distinct topics that had a review or archived paper
        reviewed_topic_ids = {
            r[0]
            for r in session.query(ArchivedTopicReview.topic_id)
            .filter(
                ArchivedTopicReview.user_id == user_id,
                ArchivedTopicReview.last_reviewed_at >= week_ago,
            )
            .all()
        }
        # add topics linked from archived papers this week
        paper_links = (
            session.query(ArchivedPaper.linked_topic_ids)
            .filter(
                ArchivedPaper.user_id == user_id,
                ArchivedPaper.archived_at >= week_ago,
            )
            .all()
        )
        for (links,) in paper_links:
            if isinstance(links, list):
                reviewed_topic_ids.update(links)
        topic_coverage = len(reviewed_topic_ids)

        # top paper of the week — highest user_rating, then highest
        # relevance_score among archived this week. None if nothing yet.
        top_paper = (
            session.query(ArchivedPaper)
            .filter(
                ArchivedPaper.user_id == user_id,
                ArchivedPaper.archived_at >= week_ago,
            )
            .order_by(
                ArchivedPaper.user_rating.desc().nullslast(),
                ArchivedPaper.relevance_score.desc().nullslast(),
            )
            .first()
        )
        top_paper_title = top_paper.title if top_paper else None
        top_paper_id = top_paper.id if top_paper else None
    finally:
        session.close()

    blind_spot = _compute_weekly_blind_spot(user_id, week_ago)

    # Compose body. Order: numbers first (cheap glance), then top paper,
    # then blind-spot suggestion (the action item).
    parts: list[str] = [
        f"{streak}-day streak",
        f"{papers_seen_week} papers seen",
        f"{topic_coverage} topics touched",
    ]
    if top_paper_title:
        parts.append(f"Top: {_strip(top_paper_title, 50)}")
    if blind_spot:
        parts.append(f"Next week: focus on {blind_spot}")
    body = " · ".join(parts)

    return {
        "title": "Your weekly Daily Scholar recap",
        "body": _strip(body, 220),
        # link to stats or archive page; archive is the actionable one
        "url": f"/archive/papers/{top_paper_id}" if top_paper_id else "/stats",
        "tag": "weekly-status",
        "data": {
            "streak": streak,
            "papers_seen_week": papers_seen_week,
            "topic_coverage": topic_coverage,
            "blind_spot": blind_spot,
        },
    }


async def build_quiz_nudge(user_id: str) -> Optional[PushPayload]:
    """
    'You have N unreviewed topics' nudge. Counts in-scope topics that
    are neither completed nor recently reviewed (3-day window matches
    the daily picker), then encourages a quick quiz.
    """
    from ..database import (
        get_completed_topic_ids,
        get_recently_reviewed_topic_ids,
    )

    scope = get_topics_for_scope(user_id=user_id)
    if not scope:
        return None

    completed = get_completed_topic_ids(user_id=user_id)
    recent = get_recently_reviewed_topic_ids(user_id=user_id, days=3)
    due = [t for t in scope if t.id not in completed and t.id not in recent]

    if not due:
        # nothing to nudge about — return None so we don't send a "0 topics" push
        logger.info("quiz_nudge: nothing due for %s", user_id)
        return None

    sample = due[0].name
    n = len(due)
    if n == 1:
        body = f"'{_strip(sample, 60)}' is ready for review."
    else:
        body = f"{n} topics ready for review, including '{_strip(sample, 60)}'."

    return {
        "title": "Quick review?",
        "body": _strip(body, 200),
        "url": "/quiz",
        "tag": "quiz-nudge",
        "data": {"due_count": n},
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


REGISTRY: dict[str, NotificationType] = {
    "study_reminder": NotificationType(
        key="study_reminder",
        label="Study reminder",
        description="Daily nudge that surfaces today's paper and review topic.",
        default_cron="0 9 * * *",          # 9am every day
        builder=build_study_reminder,
    ),
    "paper_drop": NotificationType(
        key="paper_drop",
        label="New paper",
        description="Push a fresh, unseen paper at the time you pick.",
        default_cron="0 7 * * *",          # 7am every day
        builder=build_paper_drop,
    ),
    "weekly_status": NotificationType(
        key="weekly_status",
        label="Weekly recap",
        description="Streak, papers seen, topic coverage, and next week's focus.",
        default_cron="0 18 * * 0",         # Sunday 6pm
        builder=build_weekly_status,
    ),
    "quiz_nudge": NotificationType(
        key="quiz_nudge",
        label="Quiz/review nudge",
        description="Reminder when topics are sitting unreviewed in your scope.",
        default_cron="0 20 * * *",         # 8pm every day
        builder=build_quiz_nudge,
    ),
}


def list_types() -> list[dict[str, str]]:
    """Public registry list for the settings UI (no callables)."""
    return [
        {
            "key": nt.key,
            "label": nt.label,
            "description": nt.description,
            "default_cron": nt.default_cron,
        }
        for nt in REGISTRY.values()
    ]


# fill defaults dict now that REGISTRY is populated (used by ensure_settings_shape)
DEFAULT_NOTIFICATION_SETTINGS["types"] = _registry_defaults()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def build_payload(user_id: str, type_key: str) -> Optional[PushPayload]:
    """Build (but don't send) the payload for `type_key`. None == skip."""
    nt = REGISTRY.get(type_key)
    if nt is None:
        raise KeyError(f"unknown notification type: {type_key!r}")
    return await nt.builder(user_id)


async def dispatch_notification(user_id: str, type_key: str) -> dict[str, Any]:
    """
    Build + fan out one notification. Returns a result dict with the
    push fanout counters plus a `payload` snapshot for logging.

    Used by both APScheduler jobs and the /notifications/test/{type}
    endpoint so manual tests exercise the same code path as scheduled
    sends.
    """
    from .push_sender import send_push_to_user

    nt = REGISTRY.get(type_key)
    if nt is None:
        return {"ok": False, "error": f"unknown type {type_key!r}"}

    try:
        payload = await nt.builder(user_id)
    except Exception as e:  # noqa: BLE001 — never let a builder bug kill the job
        logger.exception("notifications: builder for %s failed: %s", type_key, e)
        return {"ok": False, "type": type_key, "error": f"builder_failed: {e}"}

    if payload is None:
        # legitimate skip (e.g., quiz_nudge with nothing due)
        return {"ok": True, "type": type_key, "skipped": "empty_payload"}

    result = send_push_to_user(user_id, payload)
    logger.info(
        "notifications: dispatched %s to %s — %s", type_key, user_id, result
    )
    return {"ok": True, "type": type_key, "payload": payload, "result": result}
