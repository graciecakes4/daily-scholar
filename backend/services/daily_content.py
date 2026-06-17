"""
Daily content generation.

The HTTP endpoint at GET /daily and the APScheduler nightly job both call
`generate_daily_content()` here. Keeping the logic in one place means a
scheduled regen produces byte-identical cache rows to a user-triggered
refresh, and tests can exercise the whole pipeline without an HTTP layer.

The helpers (`_select_topic_from_scope`, `_topic_to_dict`, `_topic_pseudo_course`,
`_stream_display_name`, `_PaperLite`) used to live in main.py; they're here
now so daily_content.py is self-contained and main.py can import them too.
"""

from __future__ import annotations

import random
from datetime import date, datetime
from typing import Any, Optional

from ..database import (
    DEFAULT_USER_ID,
    DailyContentCache,
    Topic,
    get_completed_topic_ids,
    get_recently_reviewed_topic_ids,
    get_review_later_topic_ids,
    get_seen_paper_ids,
    get_session,
    get_topics_for_scope,
    mark_paper_as_seen,
    update_user_streak,
)


# ---------------------------------------------------------------------------
# Helpers (moved from main.py)
# ---------------------------------------------------------------------------


def _stream_display_name(stream: str) -> str:
    """Convert a stream slug ('photometric_classification') to a display label."""
    return (stream or "uncategorized").replace("_", " ").replace("-", " ").title()


def _topic_to_dict(topic: Topic) -> dict[str, Any]:
    """
    Serialize a Topic row into the dict shape ContentGeneratorService expects.
    Keeps course_id/course_name keys for legacy frontend compatibility — they
    now carry the topic's stream rather than a real course identifier.
    """
    return {
        "id": topic.id,
        "name": topic.name,
        "stream": topic.stream,
        "weight": topic.weight,
        "key_concepts": topic.key_concepts or [],
        "learning_objectives": topic.learning_objectives or [],
        "resources": topic.resources or [],
        "quiz_difficulty": topic.quiz_difficulty,
        "prerequisites": topic.prerequisites or [],
        "course_id": topic.stream,
        "course_name": _stream_display_name(topic.stream),
    }


def _topic_pseudo_course(topic: Topic) -> dict[str, str]:
    return {"id": topic.stream, "name": _stream_display_name(topic.stream)}


def _select_topic_from_scope(
    scope_topics: list[Topic],
    completed_ids: set[str],
    recently_reviewed_ids: set[str],
    review_later_ids: set[str],
    exclude_ids: Optional[set[str]] = None,
) -> Optional[Topic]:
    """
    Pick one Topic row out of the active scope.

    Priority:
      1. review_later that is NOT recently reviewed
      2. fresh (neither review_later nor recently reviewed)
      3. anything remaining (recently reviewed but not completed)
    """
    exclude_ids = exclude_ids or set()
    available = [
        t for t in scope_topics
        if t.id not in completed_ids and t.id not in exclude_ids
    ]
    if not available:
        return None

    review_later = [
        t for t in available
        if t.id in review_later_ids and t.id not in recently_reviewed_ids
    ]
    fresh = [
        t for t in available
        if t.id not in recently_reviewed_ids and t.id not in review_later_ids
    ]

    if review_later:
        return random.choice(review_later)
    if fresh:
        return random.choice(fresh)
    return random.choice(available)


class _PaperLite:
    """
    Adapter that lets a cached paper dict satisfy the .title/.abstract/etc.
    attribute access pattern that ContentGeneratorService.suggest_resources
    expects. Used when we regenerate review-only and need to feed the
    already-cached paper to the resources generator.
    """

    @classmethod
    def from_dict(cls, d: dict) -> "_PaperLite":
        inst = cls()
        for k, v in d.items():
            setattr(inst, k, v)
        return inst


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


VALID_REFRESH: set[str] = {"", "all", "paper", "review"}


async def generate_daily_content(
    refresh: str = "",
    user_id: str = DEFAULT_USER_ID,
    fire_push_on_new_paper: bool = True,
) -> dict[str, Any]:
    """
    Build or reuse today's daily content for `user_id`.

    Returns a dict matching the GET /daily response shape, plus a private
    `_quiz_full` key carrying the full quiz-question objects (so the HTTP
    handler can populate app.state.current_questions before returning).

    `refresh`:
      - ""       : use cache; only regenerate sections that are missing
      - "paper"  : force fresh paper + summary, keep review/quiz
      - "review" : force fresh review + quiz, keep paper
      - "all"    : regenerate everything
      - "true"   : alias for "all" (legacy)
    """
    from .paper_discovery import PaperDiscoveryService
    from .content_generator import ContentGeneratorService

    if refresh == "true":
        refresh = "all"
    if refresh not in VALID_REFRESH:
        raise ValueError(
            f"refresh must be one of {sorted(VALID_REFRESH - {''})}, got {refresh!r}"
        )

    today = date.today()

    # snapshot whatever's currently in cache (may be None)
    session = get_session()
    try:
        cached = (
            session.query(DailyContentCache)
            .filter(
                DailyContentCache.content_date == today,
                DailyContentCache.user_id == user_id,
            )
            .first()
        )
        cached_paper = cached.paper_data if cached else None
        cached_paper_summary = cached.paper_summary if cached else None
        cached_topic_reviews = cached.topic_reviews if cached else None
        cached_quiz_blob = (cached.quiz_questions if cached else None) or {}
        cached_quiz_full = (
            cached_quiz_blob.get("_full", [])
            if isinstance(cached_quiz_blob, dict)
            else []
        )
        cached_resources = cached.resources if cached else None
    finally:
        session.close()

    need_paper = (refresh in ("all", "paper")) or (cached_paper is None)
    need_review = (refresh in ("all", "review")) or (
        cached_topic_reviews is None or len(cached_topic_reviews) == 0
    )

    # cache fast path — if nothing needs regen, return cache immediately
    if not need_paper and not need_review:
        return {
            "date": today.isoformat(),
            "paper": cached_paper,
            "paper_summary": cached_paper_summary,
            "topic_reviews": cached_topic_reviews,
            "quiz": {
                "questions": cached_quiz_blob.get("display", []),
                "total_points": cached_quiz_blob.get("total_points", 0),
            },
            "resources": cached_resources,
            "estimated_time_minutes": 45,
            "cached": True,
            "_quiz_full": cached_quiz_full,
        }

    # regenerate at least one section
    discovery = PaperDiscoveryService()
    generator = ContentGeneratorService()

    try:
        # ---- paper ----
        if need_paper:
            seen_ids = list(get_seen_paper_ids())
            paper = await discovery.select_daily_paper(seen_ids=seen_ids)
            paper_payload: Optional[dict[str, Any]] = None
            paper_summary: Optional[dict[str, Any]] = None
            if paper:
                paper_payload = paper.to_dict()
                paper_payload["unique_id"] = paper.unique_id
                mark_paper_as_seen(paper_payload)
                paper_summary = await generator.generate_paper_summary(paper)
        else:
            paper = None
            paper_payload = cached_paper
            paper_summary = cached_paper_summary

        # ---- topic review + quiz ----
        if need_review:
            scope_topics = get_topics_for_scope()
            completed_ids = get_completed_topic_ids()
            recently_reviewed_ids = get_recently_reviewed_topic_ids(days=3)
            review_later_ids = get_review_later_topic_ids()

            topic_reviews: list[dict[str, Any]] = []
            quiz_questions: list[dict[str, Any]] = []
            selected = _select_topic_from_scope(
                scope_topics, completed_ids, recently_reviewed_ids, review_later_ids
            )
            if selected:
                topic_dict = _topic_to_dict(selected)
                course_dict = _topic_pseudo_course(selected)
                review = await generator.generate_topic_review(topic_dict, course_dict)
                topic_reviews.append({"topic": topic_dict, "review": review})
                questions = await generator.generate_quiz_questions(
                    topic_dict, course_dict, count=2, difficulty="medium"
                )
                quiz_questions.extend(questions)

            questions_display = [
                {
                    "id": q["id"], "topic_id": q["topic_id"],
                    "question_type": q["question_type"],
                    "question_text": q["question_text"], "options": q.get("options"),
                    "difficulty": q["difficulty"], "points": q["points"],
                }
                for q in quiz_questions
            ]
            total_points = sum(q["points"] for q in quiz_questions)
        else:
            topic_reviews = cached_topic_reviews or []
            quiz_questions = cached_quiz_full
            questions_display = cached_quiz_blob.get("display", [])
            total_points = cached_quiz_blob.get("total_points", 0)

        # ---- resources: regenerate only if either input changed ----
        if need_paper or need_review:
            topics_for_resources = [tr["topic"] for tr in topic_reviews]
            paper_for_resources = (
                paper if need_paper
                else (_PaperLite.from_dict(paper_payload) if paper_payload else None)
            )
            resources = await generator.suggest_resources(
                topics_for_resources, paper_for_resources
            )
        else:
            resources = cached_resources or []

        # persist updated cache (overwrite today's row for this user)
        session = get_session()
        try:
            existing = (
                session.query(DailyContentCache)
                .filter(
                    DailyContentCache.content_date == today,
                    DailyContentCache.user_id == user_id,
                )
                .first()
            )
            if existing:
                session.delete(existing)
                session.flush()
            session.add(
                DailyContentCache(
                    user_id=user_id,
                    content_date=today,
                    paper_unique_id=(
                        paper_payload.get("unique_id") if paper_payload else None
                    ),
                    paper_data=paper_payload,
                    paper_summary=paper_summary,
                    topic_reviews=topic_reviews,
                    quiz_questions={
                        "display": questions_display,
                        "total_points": total_points,
                        "_full": quiz_questions,
                    },
                    resources=resources,
                    generated_at=datetime.utcnow(),
                )
            )
            session.commit()
        finally:
            session.close()

        update_user_streak()

        # fire a Web Push when a NEW paper was just generated (skip review-only)
        if fire_push_on_new_paper and need_paper and paper_payload:
            try:
                from .push_sender import send_push_to_user

                send_push_to_user(
                    user_id,
                    {
                        "title": "Today's paper is ready",
                        "body": paper_payload.get("title", "")[:140],
                        "url": "/",
                        "tag": "daily-paper",
                    },
                )
            except Exception as e:  # noqa: BLE001 — push must never break the request
                print(f"push fanout failed (non-fatal): {e}")

        return {
            "date": today.isoformat(),
            "paper": paper_payload,
            "paper_summary": paper_summary,
            "topic_reviews": topic_reviews,
            "quiz": {
                "questions": questions_display,
                "total_points": total_points,
            },
            "resources": resources,
            "estimated_time_minutes": 45,
            "cached": False,
            "_quiz_full": quiz_questions,
        }
    finally:
        await discovery.close()
        await generator.close()
