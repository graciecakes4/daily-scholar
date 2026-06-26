"""
Tests for Phase D: topic search + subscription model.

Coverage:
  * subscribe rules: private rejected, system rejected, own rejected,
    duplicate rejected, happy path persists row + appears in scope
  * unsubscribe: idempotent
  * search filters: excludes system, own, private, inactive, already-subscribed
  * GET /topics now returns subscribed (not "any public") for regular users
  * get_topics_for_scope sees subscribed topics + drops unsubscribed
    + drops topics that went private after subscription
  * topic hard-delete cleans up subscriptions
  * solo `__local__` keeps seeing every system topic (no subscribe needed)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    Topic,
    TopicSubscription,
    User,
    get_session,
    get_topics_for_scope,
)
from backend.services.auth_security import hash_password
from backend.services.topic_subscriptions import (
    AlreadySubscribed,
    TopicNotFound,
    TopicNotSubscribable,
    cleanup_subscriptions_for_topic,
    is_subscribed,
    list_subscribed_topic_ids,
    subscribe,
    unsubscribe,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_user(email: str, role: str = USER_ROLE_USER) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=email.lower(),
            password_hash=hash_password("dummy12345"),
            status=USER_STATUS_ACTIVE,
            role=role,
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        session.expunge(u)
        return u
    finally:
        session.close()


def _seed_topic(
    topic_id: str,
    *,
    owner_user_id: Optional[int] = None,
    visibility: str = "public",
    name: str = "Test Topic",
    active: bool = True,
) -> Topic:
    session = get_session()
    try:
        t = Topic(
            id=topic_id, name=name, stream="testing", active=active,
            weight=1.0, keywords=["test"], arxiv_categories=[],
            recency_days=30, min_relevance=0.18,
            key_concepts=[], learning_objectives=[], resources=[],
            quiz_difficulty="medium", prerequisites=[],
            created_via="ui", source_yaml_present=False,
            owner_user_id=owner_user_id, visibility=visibility,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        session.expunge(t)
        return t
    finally:
        session.close()


def _as_email(email: str) -> dict[str, str]:
    return {"Cf-Access-Authenticated-User-Email": email}


# ---------------------------------------------------------------------------
# subscribe service: rule enforcement
# ---------------------------------------------------------------------------


class TestSubscribeService:

    def test_happy_path(self):
        owner = _seed_user("sub-owner@example.com")
        sub_user = _seed_user("sub-user@example.com")
        t = _seed_topic("sub-pub", owner_user_id=owner.id, visibility="public")

        row = subscribe(sub_user.user_id, t.id)
        assert row.topic_id == t.id
        assert is_subscribed(sub_user.user_id, t.id) is True

    def test_private_topic_rejected(self):
        owner = _seed_user("sp-owner@example.com")
        sub_user = _seed_user("sp-user@example.com")
        t = _seed_topic("sp-priv", owner_user_id=owner.id, visibility="private")
        with pytest.raises(TopicNotSubscribable):
            subscribe(sub_user.user_id, t.id)

    def test_system_topic_rejected(self):
        sub_user = _seed_user("ss-user@example.com")
        t = _seed_topic("ss-sys", owner_user_id=None, visibility="public")
        with pytest.raises(TopicNotSubscribable):
            subscribe(sub_user.user_id, t.id)

    def test_own_topic_rejected(self):
        owner = _seed_user("so-owner@example.com")
        t = _seed_topic("so-own", owner_user_id=owner.id, visibility="public")
        with pytest.raises(TopicNotSubscribable):
            subscribe(owner.user_id, t.id)

    def test_unknown_topic_rejected(self):
        sub_user = _seed_user("su-user@example.com")
        with pytest.raises(TopicNotFound):
            subscribe(sub_user.user_id, "nope-not-real")

    def test_duplicate_rejected(self):
        owner = _seed_user("sd-owner@example.com")
        sub_user = _seed_user("sd-user@example.com")
        t = _seed_topic("sd-pub", owner_user_id=owner.id, visibility="public")
        subscribe(sub_user.user_id, t.id)
        with pytest.raises(AlreadySubscribed):
            subscribe(sub_user.user_id, t.id)


class TestUnsubscribe:

    def test_unsubscribe_returns_false_when_nothing_to_drop(self):
        sub_user = _seed_user("uns-empty@example.com")
        assert unsubscribe(sub_user.user_id, "anything") is False

    def test_unsubscribe_removes_row_and_returns_true(self):
        owner = _seed_user("uns-owner@example.com")
        sub_user = _seed_user("uns-user@example.com")
        t = _seed_topic("uns-pub", owner_user_id=owner.id, visibility="public")
        subscribe(sub_user.user_id, t.id)
        assert unsubscribe(sub_user.user_id, t.id) is True
        # second call is idempotent
        assert unsubscribe(sub_user.user_id, t.id) is False


# ---------------------------------------------------------------------------
# endpoints: search + subscribe + unsubscribe
# ---------------------------------------------------------------------------


class TestSearchEndpoint:

    def test_finds_public_from_other(self, client: TestClient):
        owner = _seed_user("se-owner@example.com")
        me = _seed_user("se-me@example.com")
        _seed_topic("se-pub", owner_user_id=owner.id, visibility="public",
                    name="Machine Learning Papers")

        r = client.get("/topics/search?q=machine", headers=_as_email(me.user_id))
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert "se-pub" in ids

    def test_excludes_own(self, client: TestClient):
        me = _seed_user("seo-me@example.com")
        _seed_topic("seo-mine", owner_user_id=me.id, visibility="public",
                    name="My Searchable Topic")
        r = client.get("/topics/search?q=searchable", headers=_as_email(me.user_id))
        assert "seo-mine" not in {t["id"] for t in r.json()}

    def test_excludes_subscribed(self, client: TestClient):
        owner = _seed_user("ses-owner@example.com")
        me = _seed_user("ses-me@example.com")
        t = _seed_topic("ses-pub", owner_user_id=owner.id, visibility="public",
                        name="Subscribed Already")
        subscribe(me.user_id, t.id)
        r = client.get("/topics/search?q=subscribed", headers=_as_email(me.user_id))
        assert "ses-pub" not in {t["id"] for t in r.json()}

    def test_excludes_private(self, client: TestClient):
        owner = _seed_user("sep-owner@example.com")
        me = _seed_user("sep-me@example.com")
        _seed_topic("sep-priv", owner_user_id=owner.id, visibility="private",
                    name="Privacy Test Topic")
        r = client.get("/topics/search?q=privacy", headers=_as_email(me.user_id))
        assert "sep-priv" not in {t["id"] for t in r.json()}

    def test_excludes_inactive(self, client: TestClient):
        owner = _seed_user("sei-owner@example.com")
        me = _seed_user("sei-me@example.com")
        _seed_topic("sei-pub", owner_user_id=owner.id, visibility="public",
                    name="Inactive Test", active=False)
        r = client.get("/topics/search?q=inactive", headers=_as_email(me.user_id))
        assert "sei-pub" not in {t["id"] for t in r.json()}

    def test_case_insensitive_name_match(self, client: TestClient):
        owner = _seed_user("sec-owner@example.com")
        me = _seed_user("sec-me@example.com")
        _seed_topic("sec-pub", owner_user_id=owner.id, visibility="public",
                    name="CaseSensitivity Check")
        r = client.get("/topics/search?q=casesensitivity", headers=_as_email(me.user_id))
        assert "sec-pub" in {t["id"] for t in r.json()}


class TestSubscribeEndpoint:

    def test_post_subscribe_201(self, client: TestClient):
        owner = _seed_user("ep-owner@example.com")
        me = _seed_user("ep-me@example.com")
        t = _seed_topic("ep-pub", owner_user_id=owner.id, visibility="public")
        r = client.post(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        assert r.status_code == 201
        assert r.json()["topic_id"] == t.id

    def test_post_subscribe_409_on_duplicate(self, client: TestClient):
        owner = _seed_user("ep2-owner@example.com")
        me = _seed_user("ep2-me@example.com")
        t = _seed_topic("ep2-pub", owner_user_id=owner.id, visibility="public")
        client.post(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        r = client.post(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        assert r.status_code == 409

    def test_post_subscribe_400_on_private(self, client: TestClient):
        owner = _seed_user("ep3-owner@example.com")
        me = _seed_user("ep3-me@example.com")
        t = _seed_topic("ep3-priv", owner_user_id=owner.id, visibility="private")
        r = client.post(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        assert r.status_code == 400

    def test_post_subscribe_404_on_unknown(self, client: TestClient):
        me = _seed_user("ep4-me@example.com")
        r = client.post("/topics/does-not-exist/subscribe", headers=_as_email(me.user_id))
        assert r.status_code == 404

    def test_delete_unsubscribe_is_idempotent(self, client: TestClient):
        owner = _seed_user("ep5-owner@example.com")
        me = _seed_user("ep5-me@example.com")
        t = _seed_topic("ep5-pub", owner_user_id=owner.id, visibility="public")
        client.post(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        r1 = client.delete(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        assert r1.status_code == 200 and r1.json()["removed"] is True
        r2 = client.delete(f"/topics/{t.id}/subscribe", headers=_as_email(me.user_id))
        assert r2.status_code == 200 and r2.json()["removed"] is False


# ---------------------------------------------------------------------------
# scope + listing reflect subscription state
# ---------------------------------------------------------------------------


class TestScopeReflectsSubscriptions:

    def test_subscribed_topic_in_scope(self):
        owner = _seed_user("sr-owner@example.com")
        me = _seed_user("sr-me@example.com")
        t = _seed_topic("sr-pub", owner_user_id=owner.id, visibility="public")
        subscribe(me.user_id, t.id)
        ids = {x.id for x in get_topics_for_scope(user_id=me.user_id)}
        assert t.id in ids

    def test_unsubscribed_topic_not_in_scope(self):
        owner = _seed_user("sr2-owner@example.com")
        me = _seed_user("sr2-me@example.com")
        _seed_topic("sr2-pub", owner_user_id=owner.id, visibility="public")
        ids = {x.id for x in get_topics_for_scope(user_id=me.user_id)}
        assert "sr2-pub" not in ids

    def test_subscribed_then_private_drops_from_scope(self):
        owner = _seed_user("sr3-owner@example.com")
        me = _seed_user("sr3-me@example.com")
        t = _seed_topic("sr3-pub", owner_user_id=owner.id, visibility="public")
        subscribe(me.user_id, t.id)
        # owner flips to private
        session = get_session()
        try:
            row = session.get(Topic, t.id)
            row.visibility = "private"
            session.commit()
        finally:
            session.close()
        ids = {x.id for x in get_topics_for_scope(user_id=me.user_id)}
        assert t.id not in ids
        # but the subscription row is still there — if owner flips back,
        # the topic reappears
        assert is_subscribed(me.user_id, t.id) is True

    def test_list_topics_endpoint_shows_subscribed(self, client: TestClient):
        owner = _seed_user("lts-owner@example.com")
        me = _seed_user("lts-me@example.com")
        t = _seed_topic("lts-pub", owner_user_id=owner.id, visibility="public")
        subscribe(me.user_id, t.id)
        r = client.get("/topics", headers=_as_email(me.user_id))
        rows = r.json()
        match = next((x for x in rows if x["id"] == t.id), None)
        assert match is not None
        assert match["is_subscribed"] is True


# ---------------------------------------------------------------------------
# hard-delete cleanup
# ---------------------------------------------------------------------------


class TestHardDeleteCleanup:

    def test_hard_delete_drops_subscriptions(self, client: TestClient):
        owner = _seed_user("hd-owner@example.com")
        me = _seed_user("hd-me@example.com")
        t = _seed_topic("hd-pub", owner_user_id=owner.id, visibility="public")
        subscribe(me.user_id, t.id)

        r = client.delete(
            f"/topics/{t.id}?hard=true",
            headers=_as_email(owner.user_id),
        )
        assert r.status_code == 200
        # the subscription row should be gone, not orphaned
        session = get_session()
        try:
            remaining = (
                session.query(TopicSubscription)
                .filter(TopicSubscription.topic_id == t.id)
                .count()
            )
            assert remaining == 0
        finally:
            session.close()

    def test_cleanup_helper_returns_count(self):
        owner = _seed_user("hd2-owner@example.com")
        u1 = _seed_user("hd2-u1@example.com")
        u2 = _seed_user("hd2-u2@example.com")
        t = _seed_topic("hd2-pub", owner_user_id=owner.id, visibility="public")
        subscribe(u1.user_id, t.id)
        subscribe(u2.user_id, t.id)
        deleted = cleanup_subscriptions_for_topic(t.id)
        assert deleted == 2


# ---------------------------------------------------------------------------
# solo parity
# ---------------------------------------------------------------------------


class TestSoloParity:

    def test_solo_sees_system_topics_without_subscribing(self):
        # __local__ is admin, so the visibility filter skips entirely;
        # they see system topics without any subscribe step
        _seed_topic("solo-sys", owner_user_id=None, visibility="public")
        ids = {x.id for x in get_topics_for_scope()}    # default = __local__
        assert "solo-sys" in ids
