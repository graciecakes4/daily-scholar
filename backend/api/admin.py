"""
Admin cross-user endpoints.

These are the read-only views that let an admin inspect any user's data
— useful for supporting beta testers ("alice's stats look wrong, can
you check?") without granting raw DB access.

Auth model: every endpoint here requires `require_admin` (Phase B):

  * Solo dev (`__local__`) → admin, so local development keeps working.
  * Real users (CF Access header or in-app session) → must have a User
    row with role='admin'. Non-admins get 403.

Use `python scripts/create_admin.py --email <you>` to seed an admin row.
This closes the deferred CF-Access-only protection model from Phase 4.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

from ..auth import require_admin
from ..database import (
    USER_ROLE_ADMIN,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    DailyContentCache,
    PushSubscription,
    SeenPaper,
    Topic,
    User,
    UserSettings,
    UserStats,
    get_session,
)
from ..services.audit_log import EventType, TargetType, log_event

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    # every route inherits the in-app role gate
    dependencies=[Depends(require_admin)],
)


# every user-scoped model so /admin/users can union across them all
_USER_SCOPED_MODELS = [
    SeenPaper,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    UserStats,
    UserSettings,
    PushSubscription,
]


@admin_router.get("/users")
def list_users():
    """
    Enumerate every distinct user_id that owns rows in any user-scoped
    table, with a per-table row count. The `__local__` sentinel is
    included so admins can see legacy solo-mode data hasn't been
    migrated yet.

    Cheap query: one SELECT DISTINCT per table. Fine at beta scale
    (~30 testers); revisit if the table count grows.
    """
    session = get_session()
    try:
        per_user_counts: dict[str, dict[str, int]] = {}
        for model in _USER_SCOPED_MODELS:
            rows = (
                session.query(model.user_id, func.count(model.id))
                .group_by(model.user_id)
                .all()
            )
            for user_id, count in rows:
                per_user_counts.setdefault(user_id, {})[model.__tablename__] = count

        return {
            "user_count": len(per_user_counts),
            "users": [
                {
                    "user_id": uid,
                    "row_counts": counts,
                    "total_rows": sum(counts.values()),
                }
                for uid, counts in sorted(per_user_counts.items())
            ],
        }
    finally:
        session.close()


@admin_router.get("/users/{target_user_id}/stats")
def get_user_stats_for(target_user_id: str):
    """
    Return the UserStats row for any user, plus computed counts that the
    /stats endpoint normally derives from joined tables. Returns 404 only
    if there are zero rows for this user across every scoped table — i.e.
    the user_id has never been seen.
    """
    session = get_session()
    try:
        stats = session.query(UserStats).filter(
            UserStats.user_id == target_user_id
        ).first()

        papers_total = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == target_user_id
        ).count()
        topics_total = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == target_user_id
        ).count()
        quizzes_total = session.query(ArchivedQuiz).filter(
            ArchivedQuiz.user_id == target_user_id
        ).count()
        seen_total = session.query(SeenPaper).filter(
            SeenPaper.user_id == target_user_id
        ).count()

        if stats is None and (papers_total + topics_total + quizzes_total + seen_total) == 0:
            raise HTTPException(
                status_code=404, detail=f"no data found for user_id '{target_user_id}'",
            )

        return {
            "user_id": target_user_id,
            "lifetime": {
                "papers_seen": stats.total_papers_seen if stats else 0,
                "papers_archived": stats.total_papers_archived if stats else 0,
                "papers_completed": stats.total_papers_completed if stats else 0,
                "topics_reviewed": stats.total_topics_reviewed if stats else 0,
                "quizzes_taken": stats.total_quizzes_taken if stats else 0,
                "quiz_accuracy": round(
                    (stats.total_correct_answers / stats.total_quiz_questions * 100)
                    if stats and stats.total_quiz_questions > 0 else 0,
                    1,
                ),
            },
            "current_counts": {
                "papers": papers_total,
                "topics": topics_total,
                "quizzes": quizzes_total,
                "seen": seen_total,
            },
            "streaks": {
                "current": stats.current_streak_days if stats else 0,
                "longest": stats.longest_streak_days if stats else 0,
                "last_activity": (
                    stats.last_activity_date.isoformat()
                    if stats and stats.last_activity_date else None
                ),
            },
        }
    finally:
        session.close()


@admin_router.get("/users/{target_user_id}/papers")
def get_user_papers(
    target_user_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
):
    """
    Paginated list of archived papers for any user. Same shape as the
    public /archive/papers but without the user_id filter coming from
    the caller's identity.
    """
    import json

    session = get_session()
    try:
        query = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == target_user_id
        ).order_by(ArchivedPaper.archived_at.desc())
        if status:
            query = query.filter(ArchivedPaper.read_status == status)

        total = query.count()
        rows = query.offset(offset).limit(limit).all()

        return {
            "user_id": target_user_id,
            "total": total,
            "papers": [
                {
                    "id": p.id,
                    "unique_id": p.unique_id,
                    "title": p.title,
                    "authors": json.loads(p.authors) if p.authors else [],
                    "source": p.source,
                    "read_status": p.read_status,
                    "archived_at": p.archived_at.isoformat() if p.archived_at else None,
                }
                for p in rows
            ],
        }
    finally:
        session.close()


@admin_router.get("/whoami")
def whoami(user_id: str = Depends(require_admin)):
    """
    Debug endpoint — echoes back the identity the auth layer resolved for
    this request. Useful for verifying Cloudflare Access is wired correctly
    end-to-end without poking at user data.
    """
    return {"user_id": user_id}


# ---------------------------------------------------------------------------
# System-wide stats (ad5) — the "no cache-busting/stats endpoint exists"
# gap from FUTURE_FEATURES.md Phase 2. Fetch-then-aggregate-in-Python
# throughout rather than dialect-specific SQL (date_trunc/strftime differ
# between SQLite and Postgres) — fine at beta scale (~30 users).
# ---------------------------------------------------------------------------


@admin_router.get("/stats/overview")
def get_stats_overview():
    """
    Basic system-wide usage numbers: user counts by status, content
    volume, and a 30-day signup trend. The "how many people / how much
    stuff" view — see /admin/stats/quiz-performance for the deeper
    quiz-analytics view.
    """
    session = get_session()
    try:
        status_counts: dict[str, int] = dict(
            session.query(User.status, func.count(User.id)).group_by(User.status).all()
        )
        admin_count = session.query(User).filter(User.role == USER_ROLE_ADMIN).count()
        total_users = session.query(User).count()

        topics_total = session.query(Topic).count()
        topics_active = session.query(Topic).filter(Topic.active.is_(True)).count()

        papers_seen = session.query(SeenPaper).count()
        papers_archived = session.query(ArchivedPaper).count()
        quizzes_taken = session.query(ArchivedQuiz).count()

        # 30-day signup trend, bucketed by day in Python (not SQL) to
        # dodge date-truncation differences between SQLite and Postgres.
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_signups = (
            session.query(User.created_at)
            .filter(User.created_at >= cutoff)
            .all()
        )
        by_day: dict[str, int] = {}
        for (created_at,) in recent_signups:
            day = created_at.date().isoformat()
            by_day[day] = by_day.get(day, 0) + 1
        signup_trend = [
            {"date": day, "signups": count}
            for day, count in sorted(by_day.items())
        ]

        return {
            "users": {
                "active": status_counts.get(USER_STATUS_ACTIVE, 0),
                "pending": status_counts.get(USER_STATUS_PENDING, 0),
                "suspended": status_counts.get(USER_STATUS_SUSPENDED, 0),
                "admins": admin_count,
                "total": total_users,
            },
            "content": {
                "topics_total": topics_total,
                "topics_active": topics_active,
                "papers_seen": papers_seen,
                "papers_archived": papers_archived,
                "quizzes_taken": quizzes_taken,
            },
            "signup_trend": signup_trend,
        }
    finally:
        session.close()


# Below this participation floor, a user's accuracy is too noisy to rank
# meaningfully (e.g. 1/1 correct = a "100%" leader off a single lucky
# question). Applies only to the accuracy leaderboard, not the volume one.
_MIN_QUESTIONS_FOR_ACCURACY_LEADERBOARD = 10

# Ordering for the by-difficulty breakdown — Topic.quiz_difficulty is a
# free-text string column, not an enum, so unrecognized values sort last
# rather than erroring.
_DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


@admin_router.get("/stats/quiz-performance")
def get_quiz_performance_stats():
    """
    System-wide quiz analytics, derived entirely from ArchivedQuiz rows
    (no new instrumentation needed — each stored question already carries
    its own topic_id, difficulty, and correct/incorrect result). Answers
    the questions an admin would otherwise run ad hoc SQL for: how are
    people actually doing, which topics are people missing, is it
    getting better or worse over time, who's engaged.

    Per-question data comes from ArchivedQuiz.questions, a JSON array of
    `{..., result: {correct: bool, feedback: str} | null}` written by
    POST /archive/quizzes (see frontend/lib/api.ts::archiveQuiz). A null
    `result` (unanswered/skipped question) is treated as incorrect for
    accuracy purposes but does still count as an "attempt".
    """
    session = get_session()
    try:
        quizzes = session.query(ArchivedQuiz).order_by(ArchivedQuiz.taken_at.asc()).all()

        total_quizzes = len(quizzes)
        percentages = [q.percentage for q in quizzes if q.percentage is not None]

        total_questions_answered = 0
        total_correct = 0
        topic_stats: dict[str, dict[str, Any]] = {}
        difficulty_stats: dict[str, dict[str, int]] = {}
        score_buckets = {"0-59": 0, "60-79": 0, "80-100": 0}

        for quiz in quizzes:
            for q in (quiz.questions or []):
                total_questions_answered += 1
                result = q.get("result") or {}
                is_correct = bool(result.get("correct"))
                if is_correct:
                    total_correct += 1

                topic_id = q.get("topic_id") or "unknown"
                topic_entry = topic_stats.setdefault(
                    topic_id,
                    {"topic_name": q.get("topic_name") or topic_id, "attempts": 0, "correct": 0},
                )
                topic_entry["attempts"] += 1
                if is_correct:
                    topic_entry["correct"] += 1

                difficulty = q.get("difficulty") or "unknown"
                diff_entry = difficulty_stats.setdefault(difficulty, {"attempts": 0, "correct": 0})
                diff_entry["attempts"] += 1
                if is_correct:
                    diff_entry["correct"] += 1

            if quiz.percentage is not None:
                bucket = "0-59" if quiz.percentage < 60 else "60-79" if quiz.percentage < 80 else "80-100"
                score_buckets[bucket] += 1

        overall_accuracy = (
            round(total_correct / total_questions_answered * 100, 1)
            if total_questions_answered else 0.0
        )
        average_score = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
        median_score = round(statistics.median(percentages), 1) if percentages else 0.0

        by_topic = sorted(
            (
                {
                    "topic_id": tid,
                    "topic_name": t["topic_name"],
                    "attempts": t["attempts"],
                    "correct": t["correct"],
                    "accuracy": round(t["correct"] / t["attempts"] * 100, 1) if t["attempts"] else 0.0,
                }
                for tid, t in topic_stats.items()
            ),
            # worst-performing topics first — the actionable end of the list
            key=lambda row: row["accuracy"],
        )

        by_difficulty = sorted(
            (
                {
                    "difficulty": d,
                    "attempts": v["attempts"],
                    "correct": v["correct"],
                    "accuracy": round(v["correct"] / v["attempts"] * 100, 1) if v["attempts"] else 0.0,
                }
                for d, v in difficulty_stats.items()
            ),
            key=lambda row: _DIFFICULTY_ORDER.get(row["difficulty"], 99),
        )

        # 30-day score trend, bucketed by day in Python (same dialect-safety
        # reasoning as /admin/stats/overview's signup_trend).
        cutoff = datetime.utcnow() - timedelta(days=30)
        by_day: dict[str, list[float]] = {}
        for quiz in quizzes:
            if quiz.taken_at and quiz.taken_at >= cutoff and quiz.percentage is not None:
                day = quiz.taken_at.date().isoformat()
                by_day.setdefault(day, []).append(quiz.percentage)
        score_trend = [
            {
                "date": day,
                "quizzes_taken": len(vals),
                "avg_percentage": round(sum(vals) / len(vals), 1),
            }
            for day, vals in sorted(by_day.items())
        ]

        # leaderboards — email is denormalized here for display; UserStats
        # is keyed on the string user_id, not a User FK, so it's a
        # best-effort join against whatever User rows currently exist
        # (the '__local__' solo sentinel has none, and just shows as itself).
        email_by_user_id = {u.user_id: u.email for u in session.query(User.user_id, User.email).all()}
        active_stats = [s for s in session.query(UserStats).all() if s.total_quizzes_taken > 0]

        def _leaderboard_row(s: UserStats) -> dict[str, Any]:
            return {
                "user_id": s.user_id,
                "email": email_by_user_id.get(s.user_id, s.user_id),
                "quizzes_taken": s.total_quizzes_taken,
                "accuracy": round(
                    s.total_correct_answers / s.total_quiz_questions * 100, 1,
                ) if s.total_quiz_questions else 0.0,
            }

        top_by_volume = [
            _leaderboard_row(s)
            for s in sorted(active_stats, key=lambda s: s.total_quizzes_taken, reverse=True)[:10]
        ]

        accuracy_eligible = [
            s for s in active_stats
            if s.total_quiz_questions >= _MIN_QUESTIONS_FOR_ACCURACY_LEADERBOARD
        ]
        top_by_accuracy = [
            _leaderboard_row(s)
            for s in sorted(
                accuracy_eligible,
                key=lambda s: s.total_correct_answers / s.total_quiz_questions,
                reverse=True,
            )[:10]
        ]

        return {
            "total_quizzes": total_quizzes,
            "total_questions_answered": total_questions_answered,
            "overall_accuracy": overall_accuracy,
            "average_score": average_score,
            "median_score": median_score,
            "score_distribution": score_buckets,
            "by_topic": by_topic,
            "by_difficulty": by_difficulty,
            "score_trend": score_trend,
            "top_by_volume": top_by_volume,
            "top_by_accuracy": top_by_accuracy,
            "accuracy_leaderboard_min_questions": _MIN_QUESTIONS_FOR_ACCURACY_LEADERBOARD,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Per-user cache bust (ad5)
# ---------------------------------------------------------------------------


@admin_router.delete("/cache/{target_user_id}")
def bust_user_cache(target_user_id: str, actor_user_id: str = Depends(require_admin)) -> dict:
    """
    Delete every DailyContentCache row for this user, forcing their next
    GET /daily to regenerate from scratch instead of serving whatever's
    cached. Support-ticket tool for "my daily content looks stuck/wrong" —
    previously this required a direct DB write.

    Targeted at a single user_id only (see FUTURE_FEATURES.md Phase 6 for
    the planned multi-select + global-clear follow-up). Deletes ALL of
    that user's cache rows (every content_date), not just today's — it's
    disposable cache data, so there's no reason to be surgical about which
    day's row is stale.
    """
    session = get_session()
    try:
        deleted = (
            session.query(DailyContentCache)
            .filter(DailyContentCache.user_id == target_user_id)
            .delete(synchronize_session=False)
        )
        session.commit()
    finally:
        session.close()

    log_event(
        event_type=EventType.CACHE_BUST,
        actor_user_id_string=actor_user_id,
        target_type=TargetType.USER,
        target_id=target_user_id,
        metadata={"rows_deleted": deleted},
    )

    return {"ok": True, "user_id": target_user_id, "rows_deleted": deleted}
