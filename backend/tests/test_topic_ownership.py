"""
Tests for Phase C: per-user topic ownership + visibility.

Coverage:
  * id generator format + uniqueness behavior
  * can_view_topic / can_edit_topic permission matrix
  * POST /topics creates topic owned by caller (auto-id for regular users,
    admin override allowed)
  * PUT/DELETE /topics enforce ownership (403/404)
  * GET /topics filters: system + own + others' public; private hidden
  * get_topics_for_scope agrees with the endpoint filter
  * solo __local__ keeps seeing every NULL-owned topic (pre-Phase-C
    parity)
  * yaml-bootstrapped topics land with owner_user_id=NULL + public
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    DEFAULT_USER_ID,
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    Topic,
    User,
    get_active_topics,
    get_session,
    get_topics_for_scope,
)
from backend.services.auth_security import hash_password
from backend.services.topic_ownership import (
    USER_TOPIC_ID_PREFIX,
    can_edit_topic,
    can_view_topic,
    default_visibility,
    generate_user_topic_id,
    is_user_topic_id,
    resolve_caller,
)

from .conftest import as_user


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_user(
    email: str,
    role: str = USER_ROLE_USER,
    *,
    user_id: Optional[str] = None,
) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=(user_id or email).lower(),
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
            weight=1.0, keywords=[], arxiv_categories=[],
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
# Id generator + helpers
# ---------------------------------------------------------------------------


class TestIdGenerator:

    def test_generated_id_has_prefix(self):
        for _ in range(20):
            assert generate_user_topic_id().startswith(USER_TOPIC_ID_PREFIX)

    def test_generated_ids_distinct(self):
        ids = {generate_user_topic_id() for _ in range(50)}
        assert len(ids) == 50      # near-zero collision odds

    def test_is_user_topic_id_recognizes_prefix(self):
        assert is_user_topic_id("usr-abc123")
        assert not is_user_topic_id("photometric_classification")
        assert not is_user_topic_id("")


class TestDefaultVisibility:

    def test_null_owner_defaults_public(self):
        assert default_visibility(None) == "public"

    def test_user_owner_defaults_private(self):
        assert default_visibility(42) == "private"


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


class TestCanViewTopic:

    def test_system_topic_visible_to_everyone(self):
        owner = _seed_user("owner@example.com")
        other = _seed_user("other@example.com")
        system = _seed_topic("sys-1", owner_user_id=None, visibility="public")
        # null caller (anonymous), regular user, owner — all yes
        assert can_view_topic(system, None, False) is True
        assert can_view_topic(system, other, False) is True
        assert can_view_topic(system, owner, False) is True

    def test_private_topic_hidden_from_others(self):
        owner = _seed_user("p-owner@example.com")
        other = _seed_user("p-other@example.com")
        priv = _seed_topic("priv-1", owner_user_id=owner.id, visibility="private")
        assert can_view_topic(priv, owner, False) is True
        assert can_view_topic(priv, other, False) is False
        # admin override
        admin = _seed_user("p-admin@example.com", role=USER_ROLE_ADMIN)
        assert can_view_topic(priv, admin, True) is True

    def test_public_user_topic_visible_to_others(self):
        owner = _seed_user("pub-owner@example.com")
        other = _seed_user("pub-other@example.com")
        pub = _seed_topic("pub-1", owner_user_id=owner.id, visibility="public")
        assert can_view_topic(pub, other, False) is True


class TestCanEditTopic:

    def test_owner_can_edit_own(self):
        owner = _seed_user("e-owner@example.com")
        t = _seed_topic("e-1", owner_user_id=owner.id, visibility="private")
        assert can_edit_topic(t, owner, False) is True

    def test_other_user_cannot_edit(self):
        owner = _seed_user("e2-owner@example.com")
        other = _seed_user("e2-other@example.com")
        t = _seed_topic("e2-1", owner_user_id=owner.id, visibility="public")
        assert can_edit_topic(t, other, False) is False

    def test_admin_can_edit_anything(self):
        owner = _seed_user("e3-owner@example.com")
        admin = _seed_user("e3-admin@example.com", role=USER_ROLE_ADMIN)
        sys = _seed_topic("e3-sys", owner_user_id=None)
        own = _seed_topic("e3-own", owner_user_id=owner.id, visibility="private")
        assert can_edit_topic(sys, admin, True) is True
        assert can_edit_topic(own, admin, True) is True

    def test_no_one_but_admin_edits_system_topic(self):
        regular = _seed_user("nosys@example.com")
        sys = _seed_topic("nosys-sys", owner_user_id=None)
        assert can_edit_topic(sys, regular, False) is False


# ---------------------------------------------------------------------------
# resolve_caller
# ---------------------------------------------------------------------------


class TestResolveCaller:

    def test_solo_is_admin(self):
        caller, is_admin = resolve_caller(DEFAULT_USER_ID)
        assert caller is None and is_admin is True

    def test_real_admin(self):
        admin = _seed_user("ra-admin@example.com", role=USER_ROLE_ADMIN)
        caller, is_admin = resolve_caller(admin.user_id)
        assert caller is not None and caller.id == admin.id
        assert is_admin is True

    def test_regular_user(self):
        u = _seed_user("ra-reg@example.com")
        caller, is_admin = resolve_caller(u.user_id)
        assert caller is not None and caller.id == u.id
        assert is_admin is False

    def test_unknown_user_returns_none(self):
        caller, is_admin = resolve_caller("ghost@example.com")
        assert caller is None and is_admin is False


# ---------------------------------------------------------------------------
# /topics POST — ownership defaults
# ---------------------------------------------------------------------------


class TestTopicCreate:

    def test_regular_user_post_auto_ids_and_owns(self, client: TestClient):
        owner = _seed_user("tc-owner@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(owner.user_id),
            json={"name": "ML Papers"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"].startswith(USER_TOPIC_ID_PREFIX)
        assert body["owner_user_id"] == owner.id
        assert body["visibility"] == "private"      # default for user topics
        assert body["name"] == "ML Papers"

    def test_regular_user_cannot_override_owner(self, client: TestClient):
        owner = _seed_user("tc-cant@example.com")
        victim = _seed_user("tc-victim@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(owner.user_id),
            json={"name": "Sneaky", "owner_user_id": victim.id},
        )
        assert r.status_code == 403

    def test_two_users_can_create_same_named_topic(self, client: TestClient):
        a = _seed_user("dup-a@example.com")
        b = _seed_user("dup-b@example.com")
        r1 = client.post("/topics", headers=_as_email(a.user_id), json={"name": "ML Papers"})
        r2 = client.post("/topics", headers=_as_email(b.user_id), json={"name": "ML Papers"})
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]    # opaque auto-ids differ

    def test_admin_can_create_system_topic_with_explicit_slug(self, client: TestClient):
        admin = _seed_user("tc-admin@example.com", role=USER_ROLE_ADMIN)
        r = client.post(
            "/topics",
            headers=_as_email(admin.user_id),
            json={
                "id": "admin-system-topic",
                "name": "Admin Created System",
                "owner_user_id": None,
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["id"] == "admin-system-topic"
        assert body["owner_user_id"] is None
        assert body["visibility"] == "public"        # default for system

    def test_solo_default_creates_system_topic(self, client: TestClient):
        # no headers — solo __local__ acts as admin sentinel
        r = client.post("/topics", json={"name": "Solo Topic"})
        assert r.status_code == 201
        # solo default behavior: owner_user_id None (system) + public
        assert r.json()["owner_user_id"] is None
        assert r.json()["visibility"] == "public"


# ---------------------------------------------------------------------------
# /topics PUT / DELETE — ownership enforcement
# ---------------------------------------------------------------------------


class TestTopicEditDelete:

    def test_other_user_cannot_edit_private(self, client: TestClient):
        owner = _seed_user("ed-owner@example.com")
        other = _seed_user("ed-other@example.com")
        t = _seed_topic("ed-priv", owner_user_id=owner.id, visibility="private")
        r = client.put(
            f"/topics/{t.id}",
            headers=_as_email(other.user_id),
            json={"name": "hax"},
        )
        # other can't even see it → 404 (don't leak existence)
        assert r.status_code == 404

    def test_other_user_sees_but_cannot_edit_public(self, client: TestClient):
        owner = _seed_user("ed2-owner@example.com")
        other = _seed_user("ed2-other@example.com")
        t = _seed_topic("ed2-pub", owner_user_id=owner.id, visibility="public")
        r = client.put(
            f"/topics/{t.id}",
            headers=_as_email(other.user_id),
            json={"name": "hax"},
        )
        # other CAN view (it's public) but not edit → 403
        assert r.status_code == 403

    def test_owner_can_edit_own(self, client: TestClient):
        owner = _seed_user("ed3-owner@example.com")
        t = _seed_topic("ed3-own", owner_user_id=owner.id, visibility="private")
        r = client.put(
            f"/topics/{t.id}",
            headers=_as_email(owner.user_id),
            json={"name": "renamed"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "renamed"

    def test_admin_can_edit_anything(self, client: TestClient):
        owner = _seed_user("ed4-owner@example.com")
        admin = _seed_user("ed4-admin@example.com", role=USER_ROLE_ADMIN)
        t = _seed_topic("ed4-priv", owner_user_id=owner.id, visibility="private")
        r = client.put(
            f"/topics/{t.id}",
            headers=_as_email(admin.user_id),
            json={"name": "renamed by admin"},
        )
        assert r.status_code == 200

    def test_non_admin_cannot_delete_system_topic(self, client: TestClient):
        regular = _seed_user("del-reg@example.com")
        t = _seed_topic("del-sys", owner_user_id=None, visibility="public")
        r = client.delete(f"/topics/{t.id}", headers=_as_email(regular.user_id))
        # non-admin can view but not edit → 403
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# /topics GET — visibility filter
# ---------------------------------------------------------------------------


class TestTopicListing:

    def test_user_sees_system_own_and_others_public(self, client: TestClient):
        me = _seed_user("ls-me@example.com")
        other = _seed_user("ls-other@example.com")
        sys = _seed_topic("ls-sys", owner_user_id=None, visibility="public")
        mine = _seed_topic("ls-mine", owner_user_id=me.id, visibility="private")
        their_public = _seed_topic("ls-their-pub", owner_user_id=other.id, visibility="public")
        their_private = _seed_topic("ls-their-priv", owner_user_id=other.id, visibility="private")

        r = client.get("/topics", headers=_as_email(me.user_id))
        ids = {t["id"] for t in r.json()}
        assert sys.id in ids
        assert mine.id in ids
        assert their_public.id in ids
        assert their_private.id not in ids

    def test_admin_sees_everything(self, client: TestClient):
        admin = _seed_user("ls-admin@example.com", role=USER_ROLE_ADMIN)
        other = _seed_user("ls-victim@example.com")
        priv = _seed_topic("ls-victim-priv", owner_user_id=other.id, visibility="private")
        r = client.get("/topics", headers=_as_email(admin.user_id))
        ids = {t["id"] for t in r.json()}
        assert priv.id in ids

    def test_solo_sees_system_topics(self, client: TestClient):
        sys = _seed_topic("ls-solo-sys", owner_user_id=None, visibility="public")
        r = client.get("/topics")        # no headers = solo __local__
        ids = {t["id"] for t in r.json()}
        assert sys.id in ids

    def test_get_one_404s_for_other_users_private_topic(self, client: TestClient):
        owner = _seed_user("go-owner@example.com")
        other = _seed_user("go-other@example.com")
        priv = _seed_topic("go-priv", owner_user_id=owner.id, visibility="private")
        r = client.get(f"/topics/{priv.id}", headers=_as_email(other.user_id))
        assert r.status_code == 404         # not 403 — don't leak existence


# ---------------------------------------------------------------------------
# get_topics_for_scope agrees with the endpoint filter
# ---------------------------------------------------------------------------


class TestScopeHelper:

    def test_scope_respects_ownership(self):
        me = _seed_user("sc-me@example.com")
        other = _seed_user("sc-other@example.com")
        # add a private topic owned by `other` — should NOT appear in me's scope
        priv = _seed_topic("sc-other-priv", owner_user_id=other.id, visibility="private")
        # add a public topic owned by `other` — SHOULD appear in me's scope
        pub = _seed_topic("sc-other-pub", owner_user_id=other.id, visibility="public")

        ids = {t.id for t in get_topics_for_scope(user_id=me.user_id)}
        assert priv.id not in ids
        assert pub.id in ids

    def test_get_active_topics_user_filter(self):
        me = _seed_user("ga-me@example.com")
        other = _seed_user("ga-other@example.com")
        priv = _seed_topic("ga-priv", owner_user_id=other.id, visibility="private")
        ids = {t.id for t in get_active_topics(user_id=me.user_id)}
        assert priv.id not in ids
