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

from ..auth import get_current_user_id
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
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class TopicCreateRequest(BaseModel):
    """Body for POST /topics. id is required, all other fields optional with defaults."""

    id: str = Field(min_length=1, max_length=100)
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
):
    """List all topics, ordered by descending weight then name."""
    session = get_session()
    try:
        q = session.query(Topic)
        if stream is not None:
            q = q.filter(Topic.stream == stream)
        if active is not None:
            q = q.filter(Topic.active.is_(active))
        if not include_orphaned:
            q = q.filter(Topic.source_yaml_present.is_(True))
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


@topics_router.post("/import-yaml")
def import_yaml():
    """Re-sync the topics table from config/topics/*.yaml. Overwrites DB fields."""
    return import_topics_from_yaml()


@topics_router.post("/export-yaml")
def export_yaml():
    """Write the current DB state out to config/topics/*.yaml files."""
    return export_topics_to_yaml()


@topics_router.get("/{topic_id}", response_model=TopicResponse)
def get_topic(topic_id: str):
    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        return TopicResponse.from_model(topic)
    finally:
        session.close()


@topics_router.post("", response_model=TopicResponse, status_code=201)
def create_topic(body: TopicCreateRequest):
    session = get_session()
    try:
        if session.get(Topic, body.id) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Topic '{body.id}' already exists; PUT to update",
            )
        now = datetime.utcnow()
        topic = Topic(
            id=body.id,
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
def update_topic(topic_id: str, body: TopicUpdateRequest):
    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")

        # only apply explicitly-supplied fields
        update_data = body.model_dump(exclude_unset=True)
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
):
    """
    Soft-delete by default (active=False). Pass ?hard=true to permanently
    drop the row from the table (use with care — also clean up references
    in scope_topic_ids / prerequisites yourself).
    """
    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
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
