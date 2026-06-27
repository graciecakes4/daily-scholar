"""
Tests for Phase E: scope library.

Coverage:
  * service layer
    - create: validation, owner stamping, topic-id existence check
    - get: view-permission rules (system / public / owner / grant / denied)
    - update: edit-permission, validation respects post-update state
    - delete: explicit cleanup (active pointers, fork lineage, grants, requests)
    - set_visibility: round-trip
    - fork: lineage stamped, fork is private, copy of mode/topic_ids
    - search_public: substring on name + description, excludes private
    - list_owned_and_granted: shape with relation tag, no system scopes
    - access requests: rules (private only, no duplicate-pending, no
      self-request, no double-grant), owner inbox + approve/deny lifecycle
    - set_active / get_active: view-permission required, legacy cache refresh
  * API layer
    - status-code mapping for each error class (400 / 403 / 404 / 409)
    - 404-on-not-viewable (don't leak existence)
    - back-compat: GET /user/scope follows the active scope
  * starter content
    - seed_starter_scopes is idempotent and references real topics
  * migration script
    - materializes per-user legacy fields into Scope rows + active_scope_id
    - idempotent
    - skips users without a users-table row
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    SCOPE_REQUEST_APPROVED,
    SCOPE_REQUEST_DENIED,
    SCOPE_REQUEST_PENDING,
    SCOPE_VISIBILITY_PRIVATE,
    SCOPE_VISIBILITY_PUBLIC,
    Scope,
    ScopeAccessGrant,
    ScopeAccessRequest,
    Topic,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    User,
    UserSettings,
    get_session,
)
from backend.services import scopes as scope_service
from backend.services.auth_security import hash_password
from backend.services.scopes import (
    AccessAlreadyGranted,
    AccessRequestDuplicate,
    AccessRequestError,
    AccessRequestNotPending,
    ScopeNotEditable,
    ScopeNotFound,
    ScopeNotViewable,
    ScopeValidationError,
)
from backend.services.starter_scopes import (
    STARTER_SCOPES,
    seed_starter_scopes,
)


# ---------------------------------------------------------------------------
# shared fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    """Trigger the FastAPI lifespan once so Alembic + bootstrap runs."""
    from backend.main import app
    with TestClient(app):
        pass


def _seed_user(email: str, *, role: str = USER_ROLE_USER) -> User:
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


def _seed_topic(topic_id: str) -> Topic:
    """Minimal Topic row used as a scope_topic_ids target."""
    session = get_session()
    try:
        t = Topic(
            id=topic_id, name=topic_id, stream="testing", active=True,
            weight=1.0, keywords=[], arxiv_categories=[],
            recency_days=30, min_relevance=0.18,
            key_concepts=[], learning_objectives=[], resources=[],
            quiz_difficulty="medium", prerequisites=[],
            created_via="ui", source_yaml_present=False,
            owner_user_id=None, visibility="public",
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        session.expunge(t)
        return t
    finally:
        session.close()


def _as(uid: str) -> dict[str, str]:
    return {"X-User-Id": uid}


# ===========================================================================
# Service layer — create
# ===========================================================================


class TestCreate:

    def test_happy_path_owner_stamped(self):
        alice = _seed_user("create-a@example.com")
        _seed_topic("topic-a")
        s = scope_service.create_scope(
            alice.user_id, name="My Scope",
            scope_mode="multi", scope_topic_ids=["topic-a"],
        )
        assert s.id is not None
        assert s.owner_user_id == alice.id
        assert s.visibility == SCOPE_VISIBILITY_PRIVATE
        assert s.scope_topic_ids == ["topic-a"]

    def test_validation_blank_name(self):
        alice = _seed_user("create-blank@example.com")
        with pytest.raises(ScopeValidationError, match="name"):
            scope_service.create_scope(
                alice.user_id, name="   ", scope_mode="all",
            )

    def test_validation_silo_requires_one(self):
        alice = _seed_user("create-silo@example.com")
        _seed_topic("t1"); _seed_topic("t2")
        with pytest.raises(ScopeValidationError, match="silo"):
            scope_service.create_scope(
                alice.user_id, name="x", scope_mode="silo",
                scope_topic_ids=["t1", "t2"],
            )

    def test_validation_multi_requires_one(self):
        alice = _seed_user("create-multi@example.com")
        with pytest.raises(ScopeValidationError, match="multi"):
            scope_service.create_scope(
                alice.user_id, name="x", scope_mode="multi",
                scope_topic_ids=[],
            )

    def test_validation_unknown_topic_id(self):
        alice = _seed_user("create-unk@example.com")
        with pytest.raises(ScopeValidationError, match="unknown topic"):
            scope_service.create_scope(
                alice.user_id, name="x", scope_mode="multi",
                scope_topic_ids=["does-not-exist"],
            )

    def test_topic_ids_deduped(self):
        alice = _seed_user("create-dup@example.com")
        _seed_topic("dup-t")
        s = scope_service.create_scope(
            alice.user_id, name="x", scope_mode="multi",
            scope_topic_ids=["dup-t", "dup-t"],
        )
        assert s.scope_topic_ids == ["dup-t"]


# ===========================================================================
# Service layer — view / edit permissions
# ===========================================================================


class TestPermissions:

    def test_owner_can_view(self):
        alice = _seed_user("perm-own@example.com")
        s = scope_service.create_scope(alice.user_id, name="mine")
        got = scope_service.get_scope(alice.user_id, s.id)
        assert got.id == s.id

    def test_stranger_cannot_view_private(self):
        alice = _seed_user("perm-pa@example.com")
        bob = _seed_user("perm-pb@example.com")
        s = scope_service.create_scope(alice.user_id, name="mine")
        with pytest.raises(ScopeNotViewable):
            scope_service.get_scope(bob.user_id, s.id)

    def test_anyone_can_view_public(self):
        alice = _seed_user("perm-pubA@example.com")
        bob = _seed_user("perm-pubB@example.com")
        s = scope_service.create_scope(
            alice.user_id, name="public!", visibility="public",
        )
        got = scope_service.get_scope(bob.user_id, s.id)
        assert got.name == "public!"

    def test_grantee_can_view_private(self):
        alice = _seed_user("perm-gA@example.com")
        bob = _seed_user("perm-gB@example.com")
        s = scope_service.create_scope(alice.user_id, name="mine")
        # flip public so bob can request, then approve
        scope_service.set_visibility(alice.user_id, s.id, "public")
        scope_service.set_visibility(alice.user_id, s.id, "private")
        req = scope_service.request_access(bob.user_id, s.id)
        scope_service.decide_request(alice.user_id, req.id, approve=True)
        got = scope_service.get_scope(bob.user_id, s.id)
        assert got.id == s.id

    def test_stranger_cannot_edit_public(self):
        alice = _seed_user("perm-eA@example.com")
        bob = _seed_user("perm-eB@example.com")
        s = scope_service.create_scope(
            alice.user_id, name="mine", visibility="public",
        )
        with pytest.raises(ScopeNotEditable):
            scope_service.update_scope(bob.user_id, s.id, name="hijacked")


# ===========================================================================
# Service layer — fork
# ===========================================================================


class TestFork:

    def test_fork_stamps_lineage(self):
        alice = _seed_user("fork-a@example.com")
        bob = _seed_user("fork-b@example.com")
        _seed_topic("fork-t")
        src = scope_service.create_scope(
            alice.user_id, name="orig", visibility="public",
            scope_mode="multi", scope_topic_ids=["fork-t"],
        )
        fk = scope_service.fork_scope(bob.user_id, src.id)
        assert fk.forked_from_scope_id == src.id
        assert fk.owner_user_id == bob.id
        # forks start private regardless of source
        assert fk.visibility == SCOPE_VISIBILITY_PRIVATE
        # mode + topic ids copied
        assert fk.scope_mode == "multi"
        assert fk.scope_topic_ids == ["fork-t"]

    def test_fork_default_name(self):
        alice = _seed_user("fork-nA@example.com")
        bob = _seed_user("fork-nB@example.com")
        src = scope_service.create_scope(
            alice.user_id, name="cool stuff", visibility="public",
        )
        fk = scope_service.fork_scope(bob.user_id, src.id)
        assert fk.name == "Fork of cool stuff"

    def test_cannot_fork_unviewable(self):
        alice = _seed_user("fork-uA@example.com")
        bob = _seed_user("fork-uB@example.com")
        src = scope_service.create_scope(alice.user_id, name="private")
        with pytest.raises(ScopeNotViewable):
            scope_service.fork_scope(bob.user_id, src.id)


# ===========================================================================
# Service layer — search + library
# ===========================================================================


class TestSearchAndLibrary:

    def test_search_finds_public_excludes_private(self):
        alice = _seed_user("srch-a@example.com")
        pub = scope_service.create_scope(
            alice.user_id, name="kapow", description="findable",
            visibility="public",
        )
        scope_service.create_scope(
            alice.user_id, name="kapow private", visibility="private",
        )
        results = scope_service.search_public(alice.user_id, query="kapow")
        ids = {s.id for s in results}
        assert pub.id in ids
        assert len(ids) == 1  # private excluded

    def test_search_substring_on_description(self):
        alice = _seed_user("srch-d@example.com")
        s = scope_service.create_scope(
            alice.user_id, name="aaa",
            description="this mentions banana",
            visibility="public",
        )
        results = scope_service.search_public(alice.user_id, query="banana")
        assert any(r.id == s.id for r in results)

    def test_library_owned_and_granted(self):
        alice = _seed_user("lib-A@example.com")
        bob = _seed_user("lib-B@example.com")
        # bob owns one
        own = scope_service.create_scope(bob.user_id, name="bob owns")
        # alice owns one + grants bob
        granted = scope_service.create_scope(alice.user_id, name="alice owns")
        scope_service.set_visibility(alice.user_id, granted.id, "public")
        scope_service.set_visibility(alice.user_id, granted.id, "private")
        req = scope_service.request_access(bob.user_id, granted.id)
        scope_service.decide_request(alice.user_id, req.id, approve=True)

        lib = scope_service.list_owned_and_granted(bob.user_id)
        by_id = {s.id: rel for s, rel in lib}
        assert by_id[own.id] == "owned"
        assert by_id[granted.id] == "granted"


# ===========================================================================
# Service layer — access requests
# ===========================================================================


class TestAccessRequests:

    def test_request_then_approve_creates_grant(self):
        alice = _seed_user("req-aA@example.com")
        bob = _seed_user("req-aB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        req = scope_service.request_access(bob.user_id, s.id)
        assert req.status == SCOPE_REQUEST_PENDING

        decided = scope_service.decide_request(alice.user_id, req.id, approve=True)
        assert decided.status == SCOPE_REQUEST_APPROVED

        session = get_session()
        try:
            grant = (
                session.query(ScopeAccessGrant)
                .filter(
                    ScopeAccessGrant.scope_id == s.id,
                    ScopeAccessGrant.user_id == bob.user_id,
                )
                .first()
            )
            assert grant is not None
        finally:
            session.close()

    def test_request_then_deny_no_grant(self):
        alice = _seed_user("req-dA@example.com")
        bob = _seed_user("req-dB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        req = scope_service.request_access(bob.user_id, s.id)
        decided = scope_service.decide_request(alice.user_id, req.id, approve=False)
        assert decided.status == SCOPE_REQUEST_DENIED

        session = get_session()
        try:
            assert (
                session.query(ScopeAccessGrant)
                .filter(ScopeAccessGrant.scope_id == s.id)
                .count()
                == 0
            )
        finally:
            session.close()

    def test_duplicate_pending_rejected(self):
        alice = _seed_user("req-dupA@example.com")
        bob = _seed_user("req-dupB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        scope_service.request_access(bob.user_id, s.id)
        with pytest.raises(AccessRequestDuplicate):
            scope_service.request_access(bob.user_id, s.id)

    def test_denied_can_be_resubmitted(self):
        alice = _seed_user("req-rA@example.com")
        bob = _seed_user("req-rB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        r1 = scope_service.request_access(bob.user_id, s.id)
        scope_service.decide_request(alice.user_id, r1.id, approve=False)
        r2 = scope_service.request_access(bob.user_id, s.id)
        assert r2.id != r1.id
        assert r2.status == SCOPE_REQUEST_PENDING

    def test_public_scope_rejected(self):
        alice = _seed_user("req-puA@example.com")
        bob = _seed_user("req-puB@example.com")
        s = scope_service.create_scope(
            alice.user_id, name="x", visibility="public",
        )
        with pytest.raises(AccessRequestError):
            scope_service.request_access(bob.user_id, s.id)

    def test_owner_self_request_rejected(self):
        alice = _seed_user("req-self@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        with pytest.raises(AccessAlreadyGranted):
            scope_service.request_access(alice.user_id, s.id)

    def test_already_granted_rejected(self):
        alice = _seed_user("req-gA@example.com")
        bob = _seed_user("req-gB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        r = scope_service.request_access(bob.user_id, s.id)
        scope_service.decide_request(alice.user_id, r.id, approve=True)
        with pytest.raises(AccessAlreadyGranted):
            scope_service.request_access(bob.user_id, s.id)

    def test_double_decide_rejected(self):
        alice = _seed_user("req-ddA@example.com")
        bob = _seed_user("req-ddB@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        r = scope_service.request_access(bob.user_id, s.id)
        scope_service.decide_request(alice.user_id, r.id, approve=True)
        with pytest.raises(AccessRequestNotPending):
            scope_service.decide_request(alice.user_id, r.id, approve=False)


# ===========================================================================
# Service layer — set_active / get_active
# ===========================================================================


class TestActive:

    def test_set_get_active(self):
        alice = _seed_user("act-a@example.com")
        _seed_topic("act-t")
        s = scope_service.create_scope(
            alice.user_id, name="x", scope_mode="multi",
            scope_topic_ids=["act-t"],
        )
        scope_service.set_active(alice.user_id, s.id)
        got = scope_service.get_active(alice.user_id)
        assert got is not None and got.id == s.id

    def test_set_active_refreshes_legacy_cache(self):
        alice = _seed_user("act-c@example.com")
        _seed_topic("cache-t")
        s = scope_service.create_scope(
            alice.user_id, name="x", scope_mode="multi",
            scope_topic_ids=["cache-t"],
        )
        us = scope_service.set_active(alice.user_id, s.id)
        assert us.scope_mode == "multi"
        assert us.scope_topic_ids == ["cache-t"]

    def test_clear_active(self):
        alice = _seed_user("act-cl@example.com")
        s = scope_service.create_scope(alice.user_id, name="x")
        scope_service.set_active(alice.user_id, s.id)
        scope_service.set_active(alice.user_id, None)
        assert scope_service.get_active(alice.user_id) is None

    def test_cannot_activate_unviewable(self):
        alice = _seed_user("act-uA@example.com")
        bob = _seed_user("act-uB@example.com")
        s = scope_service.create_scope(alice.user_id, name="private")
        with pytest.raises(ScopeNotViewable):
            scope_service.set_active(bob.user_id, s.id)


# ===========================================================================
# Service layer — delete cleanup
# ===========================================================================


class TestDeleteCleanup:

    def test_delete_clears_active_pointers_breaks_forks_drops_relations(self):
        alice = _seed_user("del-A@example.com")
        bob = _seed_user("del-B@example.com")
        src = scope_service.create_scope(
            alice.user_id, name="src", visibility="public",
        )
        fk = scope_service.fork_scope(bob.user_id, src.id)
        # flip private; bob requests + alice approves so a grant exists
        scope_service.set_visibility(alice.user_id, src.id, "private")
        req = scope_service.request_access(bob.user_id, src.id)
        scope_service.decide_request(alice.user_id, req.id, approve=True)
        scope_service.set_active(bob.user_id, src.id)

        scope_service.delete_scope(alice.user_id, src.id)

        session = get_session()
        try:
            assert (
                session.query(ScopeAccessGrant)
                .filter(ScopeAccessGrant.scope_id == src.id).count() == 0
            )
            assert (
                session.query(ScopeAccessRequest)
                .filter(ScopeAccessRequest.scope_id == src.id).count() == 0
            )
            fk_row = session.query(Scope).filter(Scope.id == fk.id).first()
            assert fk_row.forked_from_scope_id is None
            us = (
                session.query(UserSettings)
                .filter(UserSettings.user_id == bob.user_id).first()
            )
            assert us.active_scope_id is None
        finally:
            session.close()


# ===========================================================================
# API layer — error mapping + back-compat
# ===========================================================================


class TestAPIErrors:

    def test_view_private_returns_404_not_403(self, client: TestClient):
        alice = _seed_user("api-vA@example.com")
        bob = _seed_user("api-vB@example.com")
        r = client.post("/scopes", headers=_as(alice.user_id),
                        json={"name": "p"})
        sid = r.json()["id"]
        r = client.get(f"/scopes/{sid}", headers=_as(bob.user_id))
        # 404 not 403 — don't leak private-scope existence
        assert r.status_code == 404

    def test_edit_others_scope_403(self, client: TestClient):
        alice = _seed_user("api-eA@example.com")
        bob = _seed_user("api-eB@example.com")
        r = client.post(
            "/scopes", headers=_as(alice.user_id),
            json={"name": "p", "visibility": "public"},
        )
        sid = r.json()["id"]
        r = client.put(f"/scopes/{sid}", headers=_as(bob.user_id),
                       json={"name": "hijacked"})
        assert r.status_code == 403

    def test_validation_400(self, client: TestClient):
        alice = _seed_user("api-vd@example.com")
        r = client.post("/scopes", headers=_as(alice.user_id),
                        json={"name": "x", "scope_mode": "silo",
                              "scope_topic_ids": []})
        assert r.status_code == 400

    def test_duplicate_request_409(self, client: TestClient):
        alice = _seed_user("api-rA@example.com")
        bob = _seed_user("api-rB@example.com")
        r = client.post("/scopes", headers=_as(alice.user_id),
                        json={"name": "p"})
        sid = r.json()["id"]
        client.post(f"/scopes/{sid}/access-requests",
                    headers=_as(bob.user_id), json={})
        r = client.post(f"/scopes/{sid}/access-requests",
                        headers=_as(bob.user_id), json={})
        assert r.status_code == 409

    def test_legacy_user_scope_follows_active(self, client: TestClient):
        """
        GET /user/scope is the legacy shim; it must reflect the active scope
        so existing paper discovery / quiz code keeps working unchanged.
        """
        alice = _seed_user("api-bc@example.com")
        _seed_topic("bc-t")
        r = client.post(
            "/scopes", headers=_as(alice.user_id),
            json={"name": "act", "scope_mode": "multi",
                  "scope_topic_ids": ["bc-t"]},
        )
        sid = r.json()["id"]
        client.put("/user/active-scope", headers=_as(alice.user_id),
                   json={"scope_id": sid})
        r = client.get("/user/scope", headers=_as(alice.user_id))
        assert r.status_code == 200
        body = r.json()
        assert body["scope_mode"] == "multi"
        assert body["scope_topic_ids"] == ["bc-t"]


# ===========================================================================
# Starter scopes
# ===========================================================================


class TestStarterScopes:

    def test_starter_count_matches_catalog(self):
        # boot already ran seeding during the schema-init fixture
        seed_starter_scopes()
        session = get_session()
        try:
            n = (
                session.query(Scope)
                .filter(Scope.owner_user_id.is_(None))
                .count()
            )
            assert n == len(STARTER_SCOPES)
        finally:
            session.close()

    def test_starter_seed_is_idempotent(self):
        first = seed_starter_scopes()
        second = seed_starter_scopes()
        # second run can't insert anything new
        assert second["inserted"] == 0
        # everything either unchanged or refreshed
        assert (
            second["unchanged"] + second["refreshed"] == len(STARTER_SCOPES)
        )

    def test_starter_topic_ids_resolve(self):
        seed_starter_scopes()
        session = get_session()
        try:
            for sc in session.query(Scope).filter(
                Scope.owner_user_id.is_(None)
            ).all():
                # every referenced topic id must actually exist
                for tid in (sc.scope_topic_ids or []):
                    assert (
                        session.query(Topic.id)
                        .filter(Topic.id == tid).first() is not None
                    ), f"starter {sc.name!r} references missing topic {tid!r}"
        finally:
            session.close()


# ===========================================================================
# Migration script
# ===========================================================================


class TestMigration:

    def _import_mig(self):
        # late import: the script lives outside the backend package
        import importlib
        return importlib.import_module("scripts.migrate_to_scope_library")

    def test_materializes_legacy_settings(self):
        mig = self._import_mig()
        alice = _seed_user("mig-a@example.com")
        # seed a legacy-style UserSettings row
        session = get_session()
        try:
            us = UserSettings(
                user_id=alice.user_id,
                scope_mode="multi",
                scope_topic_ids=["x", "y"],
            )
            session.add(us)
            session.commit()
        finally:
            session.close()

        rc = mig.migrate(apply=True)
        assert rc == 0

        session = get_session()
        try:
            us = (
                session.query(UserSettings)
                .filter(UserSettings.user_id == alice.user_id).first()
            )
            assert us.active_scope_id is not None
            sc = session.query(Scope).filter(
                Scope.id == us.active_scope_id
            ).first()
            assert sc.owner_user_id == alice.id
            assert sc.name == "My scope"
            assert sc.scope_mode == "multi"
            assert sc.scope_topic_ids == ["x", "y"]
            assert sc.visibility == SCOPE_VISIBILITY_PRIVATE
        finally:
            session.close()

    def test_idempotent(self):
        mig = self._import_mig()
        alice = _seed_user("mig-i@example.com")
        session = get_session()
        try:
            session.add(UserSettings(
                user_id=alice.user_id, scope_mode="all", scope_topic_ids=[],
            ))
            session.commit()
        finally:
            session.close()

        mig.migrate(apply=True)
        session = get_session()
        try:
            before = session.query(Scope).filter(
                Scope.owner_user_id == alice.id
            ).count()
        finally:
            session.close()

        mig.migrate(apply=True)
        session = get_session()
        try:
            after = session.query(Scope).filter(
                Scope.owner_user_id == alice.id
            ).count()
        finally:
            session.close()

        assert before == after == 1

    def test_skips_users_without_users_row(self):
        mig = self._import_mig()
        # UserSettings with a user_id that has no matching users row
        session = get_session()
        try:
            session.add(UserSettings(
                user_id="ghost@example.com",
                scope_mode="all", scope_topic_ids=[],
            ))
            session.commit()
        finally:
            session.close()

        rc = mig.migrate(apply=True)
        assert rc == 0

        session = get_session()
        try:
            us = (
                session.query(UserSettings)
                .filter(UserSettings.user_id == "ghost@example.com").first()
            )
            assert us.active_scope_id is None
        finally:
            session.close()
