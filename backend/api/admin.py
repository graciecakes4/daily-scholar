"""
Admin cross-user endpoints.

These are the read-only views that let a Cloudflare-Access-authenticated
admin inspect any user's data — useful for supporting beta testers
("alice's stats look wrong, can you check?") without granting raw DB
access.

Auth model: every endpoint here requires `require_cloudflare_access`,
which 401s in solo mode and when there's no CF Access identity at all.
There is no in-app admin role yet; access is gated entirely at the
Cloudflare Access policy layer (typically by adding an "admins" email
group to a separate Access Application that protects /admin/*).

Group-based admin enforcement (e.g., only emails in `cf_access_admin_emails`
can hit /admin) is deferred until there are enough beta testers to warrant
it. Today the assumption is: if you got past Access, you're trusted.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

from ..auth import require_cloudflare_access
from ..database import (
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    PushSubscription,
    SeenPaper,
    UserSettings,
    UserStats,
    get_session,
)

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    # every route inherits the strict CF Access requirement
    dependencies=[Depends(require_cloudflare_access)],
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
def whoami(user_id: str = Depends(require_cloudflare_access)):
    """
    Debug endpoint — echoes back the identity the auth layer resolved for
    this request. Useful for verifying Cloudflare Access is wired correctly
    end-to-end without poking at user data.
    """
    return {"user_id": user_id}
