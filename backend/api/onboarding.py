"""
Onboarding wizard endpoints (Phase E).

Three-step flow:
  1. POST /onboarding/generate-topic — turn the user's free-text
     interests into a draft topic config. Does NOT save.
  2. POST /onboarding/complete       — create the (possibly user-edited)
     topic AND flip users.onboarded=true atomically.
  3. POST /onboarding/skip           — flip users.onboarded=true without
     creating a topic (user can set one up later via /topics/new).

All endpoints require an active in-app user — solo `__local__` doesn't
have a User row to flip, so it 400s with a clear message. (Solo dev
already starts with system topics so it doesn't need onboarding.)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user_id, lookup_user_by_user_id
from ..database import (
    DEFAULT_USER_ID,
    Topic,
    User,
    get_session,
)
from ..services.onboarding import (
    InterestsTooShort,
    MAX_INTERESTS_CHARS,
    MAX_KEYWORDS,
    MIN_INTERESTS_CHARS,
    generate_topic_draft,
)
from ..services.topic_ownership import generate_user_topic_id

logger = logging.getLogger(__name__)

onboarding_router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GenerateTopicBody(BaseModel):
    interests: str = Field(
        min_length=MIN_INTERESTS_CHARS,
        max_length=MAX_INTERESTS_CHARS,
        description="Free-text description of what the user wants to learn.",
    )


class TopicDraftResponse(BaseModel):
    name: str
    keywords: list[str]
    arxiv_categories: list[str]
    key_concepts: list[str]


class CompleteOnboardingBody(BaseModel):
    """
    The wizard's third-step payload — the (possibly user-edited) draft.
    Same shape as TopicDraftResponse plus a couple of optional knobs
    that aren't worth exposing in the wizard UI but the API accepts
    for completeness.
    """

    name: str = Field(min_length=1, max_length=200)
    keywords: list[str] = Field(default_factory=list)
    arxiv_categories: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    # let the wizard let the user opt-in to public visibility on
    # their first topic if they want to share it from day one
    visibility: str = Field(default="private", pattern="^(private|public)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_active_user(user_id: str) -> User:
    """
    Resolve to a real User row. Solo `__local__` is rejected — they
    don't have a row to flip onboarded on, and their experience is
    already "everything visible" so the wizard doesn't apply.
    """
    if user_id == DEFAULT_USER_ID:
        raise HTTPException(
            status_code=400,
            detail="Onboarding is not applicable in solo dev mode.",
        )
    user = lookup_user_by_user_id(user_id)
    if user is None:
        # could happen for a CF-Access-only identity that hasn't signed
        # up in-app — the rest of the app still works for them, but
        # onboarding doesn't apply
        raise HTTPException(
            status_code=400,
            detail="No in-app user record found for this identity.",
        )
    return user


def _mark_onboarded(user_id_int: int) -> None:
    """Flip the onboarded flag. Idempotent (already-true → no-op)."""
    session = get_session()
    try:
        u = session.query(User).filter(User.id == user_id_int).first()
        if u is None:
            return
        if not u.onboarded:
            u.onboarded = True
            session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@onboarding_router.post("/generate-topic", response_model=TopicDraftResponse)
def generate_topic(
    body: GenerateTopicBody,
    user_id: str = Depends(get_current_user_id),
) -> TopicDraftResponse:
    """
    Turn free-text interests into a structured topic draft. Doesn't
    save — the wizard renders the response in editable form, the user
    tweaks, then POST /onboarding/complete persists.
    """
    _require_active_user(user_id)
    try:
        draft = generate_topic_draft(body.interests)
    except InterestsTooShort as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TopicDraftResponse(**draft.to_dict())


@onboarding_router.post("/complete", status_code=201)
def complete_onboarding(
    body: CompleteOnboardingBody,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """
    Atomically create the user's first topic + flip onboarded=true.
    Both happen in one DB session so an error in either rolls back
    both — we don't want a half-onboarded user with a phantom topic.
    """
    user = _require_active_user(user_id)

    session = get_session()
    try:
        # generate an opaque topic id (matches the auto-id behavior of
        # POST /topics for non-admin callers)
        for _ in range(5):
            candidate = generate_user_topic_id()
            if session.get(Topic, candidate) is None:
                new_id = candidate
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate a unique topic id")

        now = datetime.utcnow()
        topic = Topic(
            id=new_id,
            name=body.name.strip(),
            # wizard doesn't ask for a stream — default to a neutral bucket
            stream="onboarding",
            active=True,
            weight=1.0,
            keywords=body.keywords,
            arxiv_categories=body.arxiv_categories,
            recency_days=30,
            min_relevance=0.18,
            key_concepts=body.key_concepts,
            learning_objectives=[],
            resources=[],
            quiz_difficulty="medium",
            prerequisites=[],
            created_via="ui",
            source_yaml_present=False,
            owner_user_id=user.id,
            visibility=body.visibility,
            created_at=now,
            updated_at=now,
        )
        session.add(topic)

        # flip onboarded inside the same transaction
        u = session.query(User).filter(User.id == user.id).first()
        if u is not None:
            u.onboarded = True

        session.commit()
        session.refresh(topic)

        return {
            "ok": True,
            "topic_id": topic.id,
            "name": topic.name,
            "onboarded": True,
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.exception("complete_onboarding: %s", e)
        raise HTTPException(status_code=500, detail="Could not complete onboarding")
    finally:
        session.close()


@onboarding_router.post("/skip")
def skip_onboarding(
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Flip onboarded=true without creating a topic. Idempotent."""
    user = _require_active_user(user_id)
    _mark_onboarded(user.id)
    return {"ok": True, "onboarded": True}
