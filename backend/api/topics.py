"""
Topic CRUD + per-user scope endpoints.

Topics drive both paper discovery (via keywords + arxiv_categories) and the
review/quiz surfaces (via key_concepts + learning_objectives). They are
canonical in the DB; YAML files under config/topics/ are bootstrap + export.

Auth: scope endpoints resolve the user id via the shared `get_current_user_id`
dependency (Cf-Access header → X-User-Id → '__local__' sentinel). Flipping on
Cloudflare Access is a policy + JWT-validation change, not a code change here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user_id, require_admin
from ..database import (
    Topic,
    UserSettings,
    get_or_create_user_settings,
    get_session,
)
from ..services.topic_loader import (
    export_topics_to_yaml,
    import_topics_from_yaml,
)
from ..services.topic_ownership import (
    can_edit_topic,
    can_view_topic,
    caller_owner_id,
    default_visibility,
    generate_user_topic_id,
    resolve_caller,
)


# =============================================================================
# Pydantic schemas
# =============================================================================


class TopicResponse(BaseModel):
    """Serialized Topic row."""

    id: str
    name: str
    stream: str
    active: bool
    weight: float
    keywords: list[str]
    arxiv_categories: list[str]
    recency_days: int
    min_relevance: float
    key_concepts: list[str]
    learning_objectives: list[str]
    resources: list[str]
    quiz_difficulty: str
    prerequisites: list[str]
    created_via: str
    source_yaml_present: bool
    # Phase C: ownership + visibility surfaced so the UI can show
    # owner badges and visibility toggles
    owner_user_id: Optional[int]
    visibility: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, t: Topic) -> "TopicResponse":
        return cls(
            id=t.id,
            name=t.name,
            stream=t.stream,
            active=t.active,
            weight=t.weight,
            keywords=list(t.keywords or []),
            arxiv_categories=list(t.arxiv_categories or []),
            recency_days=t.recency_days,
            min_relevance=t.min_relevance,
            key_concepts=list(t.key_concepts or []),
            learning_objectives=list(t.learning_objectives or []),
            resources=list(t.resources or []),
            quiz_difficulty=t.quiz_difficulty,
            prerequisites=list(t.prerequisites or []),
            created_via=t.created_via,
            source_yaml_present=t.source_yaml_present,
            owner_user_id=t.owner_user_id,
            visibility=t.visibility,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class TopicCreateRequest(BaseModel):
    """
    Body for POST /topics.

    Regular users: omit `id` (server auto-generates an opaque `usr-xxxxxx`
    slug) and `owner_user_id` (defaults to the caller's user.id). The
    topic is created as `visibility='private'` unless explicitly set.

    Admins: may pass `id` (any human slug) AND `owner_user_id=null` to
    create a system-wide topic, mirroring yaml-bootstrapped behavior.
    """

    id: Optional[str] = Field(default=None, max_length=100,
                              description="Admin-only override; auto-generated for regular users.")
    name: str = Field(min_length=1, max_length=200)
    stream: str = Field(default="uncategorized", max_length=100)
    active: bool = True
    weight: float = 1.0
    keywords: list[str] = Field(default_factory=list)
    arxiv_categories: list[str] = Field(default_factory=list)
    recency_days: int = 30
    min_relevance: float = 0.18
    key_concepts: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    quiz_difficulty: str = "medium"
    prerequisites: list[str] = Field(default_factory=list)
    # Phase C: ownership knobs. Both are admin-only when set explicitly;
    # regular users get the defaults.
    owner_user_id: Optional[int] = Field(
        default=None,
        description="Admin-only override; defaults to the caller's id (or NULL for admin).",
    )
    visibility: Optional[str] = Field(
        default=None,
        pattern="^(private|public)$",
        description="private (default for user topics) | public (default for system).",
    )


class TopicUpdateRequest(BaseModel):
    """Body for PUT /topics/{id}. All fields optional; supplied fields overwrite."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    stream: Optional[str] = Field(default=None, max_length=100)
    active: Optional[bool] = None
    weight: Optional[float] = None
    keywords: Optional[list[str]] = None
    arxiv_categories: Optional[list[str]] = None
    recency_days: Optional[int] = None
    min_relevance: Optional[float] = None
    key_concepts: Optional[list[str]] = None
    learning_objectives: Optional[list[str]] = None
    resources: Optional[list[str]] = None
    quiz_difficulty: Optional[str] = None
    prerequisites: Optional[list[str]] = None
    # ownership knobs admins can flip; non-admins ignore (enforced server-side)
    visibility: Optional[str] = Field(default=None, pattern="^(private|public)$")


class ScopeResponse(BaseModel):
    """Serialized UserSettings (just the scope fields for now)."""

    user_id: str
    scope_mode: str  # "silo" | "multi" | "all"
    scope_topic_ids: list[str]
    updated_at: datetime


class ScopeUpdateRequest(BaseModel):
    """Body for PUT /user/scope."""

    scope_mode: str = Field(pattern="^(silo|multi|all)$")
    scope_topic_ids: list[str] = Field(default_factory=list)


# =============================================================================
# routers
# =============================================================================

topics_router = APIRouter(prefix="/topics", tags=["Topics"])
scope_router = APIRouter(prefix="/user", tags=["User"])


# ---------------------------------------------------------------------------
# Topic CRUD
# ---------------------------------------------------------------------------


@topics_router.get("", response_model=list[TopicResponse])
def list_topics(
    stream: Optional[str] = Query(default=None, description="Filter by stream"),
    active: Optional[bool] = Query(default=None, description="Filter by active flag"),
    include_orphaned: bool = Query(
        default=True,
        description="Include topics whose YAML file is no longer on disk",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """
    List topics the caller is allowed to see, ordered by descending weight
    then name. Ownership rules:
      - system topics (owner IS NULL) → visible to everyone
      - admins (incl. solo __local__) → see everything
      - regular users → see system + their own + other users' public topics
    Phase D will add subscription filtering on top of this.
    """
    caller, is_admin = resolve_caller(user_id)

    session = get_session()
    try:
        q = session.query(Topic)
        if stream is not None:
            q = q.filter(Topic.stream == stream)
        if active is not None:
            q = q.filter(Topic.active.is_(active))
        if not include_orphaned:
            q = q.filter(Topic.source_yaml_present.is_(True))

        # ownership filter — admins skip it, everyone else gets
        # system + own + public-from-others
        if not is_admin:
            from sqlalchemy import or_
            clauses = [Topic.owner_user_id.is_(None), Topic.visibility == "public"]
            if caller is not None:
                clauses.append(Topic.owner_user_id == caller.id)
            q = q.filter(or_(*clauses))

        q = q.order_by(Topic.weight.desc(), Topic.name.asc())
        rows = q.all()
        return [TopicResponse.from_model(t) for t in rows]
    finally:
        session.close()


@topics_router.get("/streams")
def list_streams():
    """Return the distinct stream tags currently in use, for UI grouping."""
    session = get_session()
    try:
        rows = session.query(Topic.stream).distinct().all()
        return {"streams": sorted({r[0] for r in rows if r[0]})}
    finally:
        session.close()


@topics_router.post("/import-yaml", dependencies=[Depends(require_admin)])
def import_yaml():
    """Re-sync the topics table from config/topics/*.yaml. Admin-only because it mutates system topics."""
    return import_topics_from_yaml()


@topics_router.post("/export-yaml", dependencies=[Depends(require_admin)])
def export_yaml():
    """Write the current DB state out to config/topics/*.yaml files. Admin-only."""
    return export_topics_to_yaml()


@topics_router.get("/{topic_id}", response_model=TopicResponse)
def get_topic(topic_id: str, user_id: str = Depends(get_current_user_id)):
    caller, is_admin = resolve_caller(user_id)
    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        if not can_view_topic(topic, caller, is_admin):
            # 404 not 403 so we don't leak the existence of someone else's
            # private topic to a random caller
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        return TopicResponse.from_model(topic)
    finally:
        session.close()


@topics_router.post("", response_model=TopicResponse, status_code=201)
def create_topic(
    body: TopicCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a topic. See `TopicCreateRequest` for the per-role contract.

    Solo `__local__` is treated as admin: keeps the solo dev experience
    of "just make a topic, no owner" intact.
    """
    caller, is_admin = resolve_caller(user_id)

    # ownership: admins can override (or omit for system); regular users
    # always get themselves as owner regardless of what they posted
    if is_admin:
        # admin: respect explicit owner; default to NULL (system topic)
        owner_id = body.owner_user_id
    else:
        if caller is None:
            # logged-out caller with no User row and not solo — refuse
            raise HTTPException(status_code=403, detail="Login required to create topics")
        if body.owner_user_id is not None and body.owner_user_id != caller.id:
            raise HTTPException(
                status_code=403,
                detail="Only admins can create topics owned by another user",
            )
        owner_id = caller.id

    # id: admins may supply a slug; users always get an auto-generated
    # opaque id (server-side) so two users can't fight over the same name
    if is_admin and body.id and body.id.strip():
        new_id = body.id.strip()
    else:
        # generate, retrying on the astronomically-unlikely chance of a
        # collision with an existing row
        session_for_check = get_session()
        try:
            for _ in range(5):
                candidate = generate_user_topic_id()
                if session_for_check.get(Topic, candidate) is None:
                    new_id = candidate
                    break
            else:
                raise HTTPException(status_code=500, detail="Could not generate a unique topic id")
        finally:
            session_for_check.close()

    visibility = body.visibility or default_visibility(owner_id)

    session = get_session()
    try:
        if session.get(Topic, new_id) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Topic '{new_id}' already exists; PUT to update",
            )
        now = datetime.utcnow()
        topic = Topic(
            id=new_id,
            name=body.name,
            stream=body.stream,
            active=body.active,
            weight=body.weight,
            keywords=body.keywords,
            arxiv_categories=body.arxiv_categories,
            recency_days=body.recency_days,
            min_relevance=body.min_relevance,
            key_concepts=body.key_concepts,
            learning_objectives=body.learning_objectives,
            resources=body.resources,
            quiz_difficulty=body.quiz_difficulty,
            prerequisites=body.prerequisites,
            created_via="ui",
            source_yaml_present=False,
            owner_user_id=owner_id,
            visibility=visibility,
            created_at=now,
            updated_at=now,
        )
        session.add(topic)
        session.commit()
        session.refresh(topic)
        return TopicResponse.from_model(topic)
    finally:
        session.close()


@topics_router.put("/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: str,
    body: TopicUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    caller, is_admin = resolve_caller(user_id)

    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        if not can_edit_topic(topic, caller, is_admin):
            # don't leak existence of someone else's topic; 404 if they
            # also can't view, 403 if they can view but not edit
            if can_view_topic(topic, caller, is_admin):
                raise HTTPException(status_code=403, detail="You don't own this topic")
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")

        update_data = body.model_dump(exclude_unset=True)
        # non-admins can't change visibility on system topics (irrelevant
        # since they fail can_edit_topic anyway), and they can flip their
        # own topic's visibility freely — no extra check needed.
        for key, value in update_data.items():
            setattr(topic, key, value)
        topic.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(topic)
        return TopicResponse.from_model(topic)
    finally:
        session.close()


@topics_router.delete("/{topic_id}")
def delete_topic(
    topic_id: str,
    hard: bool = Query(
        default=False,
        description="Hard-delete the row; default is soft-delete (active=False)",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """
    Soft-delete by default (active=False). Pass ?hard=true to permanently
    drop the row from the table (use with care — also clean up references
    in scope_topic_ids / prerequisites yourself).

    Only the owner or an admin can delete; system topics are admin-only.
    """
    caller, is_admin = resolve_caller(user_id)

    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        if not can_edit_topic(topic, caller, is_admin):
            if can_view_topic(topic, caller, is_admin):
                raise HTTPException(status_code=403, detail="You don't own this topic")
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")

        if hard:
            session.delete(topic)
            session.commit()
            return {"deleted": topic_id, "mode": "hard"}
        # soft delete
        topic.active = False
        topic.updated_at = datetime.utcnow()
        session.commit()
        return {"deleted": topic_id, "mode": "soft", "active": False}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


@scope_router.get("/scope", response_model=ScopeResponse)
def get_scope(user_id: str = Depends(get_current_user_id)):
    """Return this user's topic scope (defaults to 'all')."""
    settings = get_or_create_user_settings(user_id)
    return ScopeResponse(
        user_id=settings.user_id,
        scope_mode=settings.scope_mode,
        scope_topic_ids=list(settings.scope_topic_ids or []),
        updated_at=settings.updated_at,
    )


@scope_router.put("/scope", response_model=ScopeResponse)
def update_scope(
    body: ScopeUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Update scope mode + selected topic ids for this user.

    Validation:
      - silo: exactly one topic id in scope_topic_ids
      - multi: at least one topic id, all must exist
      - all: scope_topic_ids ignored (kept for round-trip but not used)
    """
    if body.scope_mode == "silo" and len(body.scope_topic_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail="silo mode requires exactly one topic id",
        )
    if body.scope_mode == "multi" and not body.scope_topic_ids:
        raise HTTPException(
            status_code=400,
            detail="multi mode requires at least one topic id",
        )

    session = get_session()
    try:
        # verify each provided id exists
        if body.scope_topic_ids:
            existing = {
                r[0]
                for r in session.query(Topic.id)
                .filter(Topic.id.in_(body.scope_topic_ids))
                .all()
            }
            missing = [tid for tid in body.scope_topic_ids if tid not in existing]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown topic ids: {missing}",
                )

        settings = session.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).first()
        if settings is None:
            settings = UserSettings(user_id=user_id)
            session.add(settings)

        settings.scope_mode = body.scope_mode
        settings.scope_topic_ids = body.scope_topic_ids
        settings.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(settings)

        return ScopeResponse(
            user_id=settings.user_id,
            scope_mode=settings.scope_mode,
            scope_topic_ids=list(settings.scope_topic_ids or []),
            updated_at=settings.updated_at,
        )
    finally:
        session.close()
