"""
Topic subscription service (Phase D).

A subscription is "user X follows topic Y" — only meaningful when Y is
a public topic owned by someone else. The endpoint layer and the scope
helper both rely on these functions so the rules can't drift.

Solo `__local__` users can subscribe too (the sentinel is a valid
`user_id` string), but they almost never need to — they see every
NULL-owned topic by virtue of being admin in the visibility filter.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from ..auth import lookup_user_by_user_id
from ..database import (
    DEFAULT_USER_ID,
    Topic,
    TopicSubscription,
    get_session,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure modes (typed so endpoints can map each to a clear 4xx)
# ---------------------------------------------------------------------------


class SubscriptionError(ValueError):
    """Base class for subscribe-time failures."""


class TopicNotFound(SubscriptionError):
    """The topic id doesn't exist."""


class TopicNotSubscribable(SubscriptionError):
    """Topic exists but can't be subscribed to (private, system, your own)."""


class AlreadySubscribed(SubscriptionError):
    """You're already subscribed; refuse the duplicate row."""


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe
# ---------------------------------------------------------------------------


def subscribe(user_id: str, topic_id: str) -> TopicSubscription:
    """
    Add a subscription from `user_id` to `topic_id`.

    Rules:
      * topic must exist (TopicNotFound)
      * topic must be a user-owned, public topic (TopicNotSubscribable)
        - subscribing to a system topic is a no-op since system topics
          are already in everyone's scope
        - subscribing to your own topic is rejected — you can't follow
          yourself
        - private topics are off-limits
      * (user, topic) must be unique (AlreadySubscribed)
    """
    session = get_session()
    try:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise TopicNotFound(f"Topic '{topic_id}' not found")

        if topic.owner_user_id is None:
            raise TopicNotSubscribable("System topics are already in your scope")
        if topic.visibility != "public":
            raise TopicNotSubscribable("Only public topics can be subscribed to")

        # is this the caller's own topic? compare via the int user.id on
        # the topic vs the User row for the caller's string user_id.
        caller = lookup_user_by_user_id(user_id)
        if caller is not None and caller.id == topic.owner_user_id:
            raise TopicNotSubscribable("You already own this topic")

        row = TopicSubscription(
            user_id=user_id,
            topic_id=topic_id,
            subscribed_at=datetime.utcnow(),
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AlreadySubscribed(f"Already subscribed to '{topic_id}'")
        session.refresh(row)
        session.expunge(row)
        return row
    finally:
        session.close()


def unsubscribe(user_id: str, topic_id: str) -> bool:
    """
    Drop a subscription. Idempotent: returns False if no row existed,
    True when we actually deleted one.
    """
    session = get_session()
    try:
        row = (
            session.query(TopicSubscription)
            .filter(
                TopicSubscription.user_id == user_id,
                TopicSubscription.topic_id == topic_id,
            )
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def list_subscribed_topic_ids(user_id: str) -> set[str]:
    """All topic ids the user is subscribed to (for scope filtering)."""
    if not user_id:
        return set()
    session = get_session()
    try:
        rows = (
            session.query(TopicSubscription.topic_id)
            .filter(TopicSubscription.user_id == user_id)
            .all()
        )
        return {r[0] for r in rows}
    finally:
        session.close()


def is_subscribed(user_id: str, topic_id: str) -> bool:
    """Cheap single-row existence check used by UI / endpoint responses."""
    session = get_session()
    try:
        return (
            session.query(TopicSubscription.id)
            .filter(
                TopicSubscription.user_id == user_id,
                TopicSubscription.topic_id == topic_id,
            )
            .first()
            is not None
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Cleanup hooks
# ---------------------------------------------------------------------------


def cleanup_subscriptions_for_topic(topic_id: str) -> int:
    """
    Delete every subscription pointing at this topic. Called before a
    topic is hard-deleted so we don't leave dangling FK references
    (SQLite ignores FK CASCADE by default; Postgres would enforce it
    but we're explicit for portability).
    """
    session = get_session()
    try:
        deleted = (
            session.query(TopicSubscription)
            .filter(TopicSubscription.topic_id == topic_id)
            .delete(synchronize_session=False)
        )
        session.commit()
        return int(deleted or 0)
    finally:
        session.close()
