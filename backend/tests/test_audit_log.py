"""
Tests for the admin audit log.

Coverage:
  * log_event writes a row with all denormalized fields
  * log_event swallows DB errors (best-effort logging)
  * each admin mutation (approve/reject/role/suspend/reactivate/invite
    create/invite revoke) emits the right event_type with right actor,
    target, and metadata
  * GET /admin/audit returns events newest-first with filters and
    pagination; invalid event_type / since / until → 400
  * /admin/audit gated by require_admin (non-admin 403)
  * /admin/audit/event-types returns the closed enum
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    AdminAuditEvent,
    User,
    get_session,
)
from backend.services.audit_log import EventType, TargetType, log_event
from backend.services.auth_security import hash_password


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


ADMIN_EMAIL = "audit-admin@example.com"


def _seed_user(
    email: str,
    *,
    role: str = USER_ROLE_USER,
    status: str = USER_STATUS_ACTIVE,
) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=email.lower(),
            password_hash=hash_password("dummy12345"),
            status=status,
            role=role,
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow() if status == USER_STATUS_ACTIVE else None,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        session.expunge(u)
        return u
    finally:
        session.close()


def _seed_admin(email: str = ADMIN_EMAIL) -> User:
    return _seed_user(email, role=USER_ROLE_ADMIN)


def _as_email(email: str) -> dict[str, str]:
    return {"Cf-Access-Authenticated-User-Email": email}


def _latest_event_for_actor(actor: str) -> AdminAuditEvent | None:
    session = get_session()
    try:
        return (
            session.query(AdminAuditEvent)
            .filter(AdminAuditEvent.actor_user_id_string == actor)
            .order_by(AdminAuditEvent.created_at.desc())
            .first()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# log_event service unit
# ---------------------------------------------------------------------------


class TestLogEventHelper:

    def test_writes_row_with_denormalized_fields(self):
        admin = _seed_admin("le-admin@example.com")
        log_event(
            event_type=EventType.USER_APPROVE,
            actor_user_id_string=admin.user_id,
            target_type=TargetType.USER,
            target_id="some-target@example.com",
            target_label="some-target@example.com",
            metadata={"approved_at": "2026-06-26T00:00:00"},
        )
        row = _latest_event_for_actor(admin.user_id)
        assert row is not None
        assert row.event_type == EventType.USER_APPROVE
        assert row.actor_user_id == admin.id        # FK resolved
        assert row.target_type == "user"
        assert row.target_id == "some-target@example.com"
        assert row.audit_metadata.get("approved_at") == "2026-06-26T00:00:00"

    def test_swallows_errors(self, monkeypatch):
        """Best-effort: a DB hiccup in log_event must not raise."""
        from backend.services import audit_log as audit_log_mod

        class _BoomSession:
            def add(self, *a, **kw): raise RuntimeError("simulated DB failure")
            def commit(self): raise RuntimeError("never reached")
            def close(self): pass

        monkeypatch.setattr(audit_log_mod, "get_session", lambda: _BoomSession())
        # should NOT raise
        log_event(
            event_type=EventType.USER_APPROVE,
            actor_user_id_string="anyone",
            target_type=TargetType.USER,
        )

    def test_solo_actor_leaves_fk_null(self):
        from backend.database import DEFAULT_USER_ID
        log_event(
            event_type=EventType.INVITE_CREATE,
            actor_user_id_string=DEFAULT_USER_ID,
            target_type=TargetType.INVITE,
            target_id="solo-test-code",
            target_label="solo-test-code",
        )
        session = get_session()
        try:
            row = (
                session.query(AdminAuditEvent)
                .filter(AdminAuditEvent.target_id == "solo-test-code")
                .first()
            )
            assert row is not None
            assert row.actor_user_id is None     # no FK for __local__
            assert row.actor_user_id_string == DEFAULT_USER_ID
        finally:
            session.close()


# ---------------------------------------------------------------------------
# admin endpoints emit audit events
# ---------------------------------------------------------------------------


class TestAdminEndpointsEmitEvents:

    def test_approve_logs_user_approve(self, client: TestClient):
        _seed_admin()
        target = _seed_user("e-approve@example.com", status=USER_STATUS_PENDING)
        r = client.post(
            f"/admin/approvals/{target.id}/approve",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 200
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None
        assert ev.event_type == EventType.USER_APPROVE
        assert ev.target_id == "e-approve@example.com"
        assert ev.target_label == "e-approve@example.com"

    def test_reject_logs_user_reject(self, client: TestClient):
        _seed_admin()
        target = _seed_user("e-reject@example.com", status=USER_STATUS_PENDING)
        r = client.post(
            f"/admin/approvals/{target.id}/reject",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 200
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.USER_REJECT
        assert ev.target_id == "e-reject@example.com"
        assert ev.audit_metadata.get("deleted") is True

    def test_role_change_logs_with_old_and_new(self, client: TestClient):
        _seed_admin()
        target = _seed_user("e-role@example.com")
        r = client.put(
            f"/admin/accounts/{target.user_id}/role",
            headers=_as_email(ADMIN_EMAIL),
            json={"role": "admin"},
        )
        assert r.status_code == 200
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.USER_ROLE_CHANGE
        assert ev.audit_metadata.get("old_role") == "user"
        assert ev.audit_metadata.get("new_role") == "admin"

    def test_suspend_logs_user_suspend_with_status_delta(self, client: TestClient):
        _seed_admin()
        target = _seed_user("e-suspend@example.com")
        r = client.put(
            f"/admin/accounts/{target.user_id}/status",
            headers=_as_email(ADMIN_EMAIL),
            json={"status": "suspended"},
        )
        assert r.status_code == 200
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.USER_SUSPEND
        assert ev.audit_metadata.get("old_status") == "active"
        assert ev.audit_metadata.get("new_status") == "suspended"

    def test_reactivate_logs_user_reactivate(self, client: TestClient):
        _seed_admin()
        target = _seed_user("e-react@example.com", status=USER_STATUS_SUSPENDED)
        r = client.put(
            f"/admin/accounts/{target.user_id}/status",
            headers=_as_email(ADMIN_EMAIL),
            json={"status": "active"},
        )
        assert r.status_code == 200
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.USER_REACTIVATE

    def test_invite_create_logs_with_max_uses(self, client: TestClient):
        _seed_admin()
        r = client.post(
            "/admin/invites",
            headers=_as_email(ADMIN_EMAIL),
            json={"max_uses": 3},
        )
        assert r.status_code == 201
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.INVITE_CREATE
        assert ev.audit_metadata.get("max_uses") == 3
        assert ev.target_id == r.json()["invite"]["code"]

    def test_invite_revoke_logs_and_skips_on_unknown(self, client: TestClient):
        _seed_admin()
        created = client.post(
            "/admin/invites",
            headers=_as_email(ADMIN_EMAIL),
            json={"max_uses": 1},
        )
        invite_id = created.json()["invite"]["id"]

        # successful revoke → logs
        client.delete(f"/admin/invites/{invite_id}", headers=_as_email(ADMIN_EMAIL))
        ev = _latest_event_for_actor(ADMIN_EMAIL)
        assert ev is not None and ev.event_type == EventType.INVITE_REVOKE

        # capture event count BEFORE the no-op revoke
        session = get_session()
        try:
            count_before = (
                session.query(AdminAuditEvent)
                .filter(AdminAuditEvent.event_type == EventType.INVITE_REVOKE)
                .count()
            )
        finally:
            session.close()

        # second revoke → no flip → no log
        client.delete(f"/admin/invites/{invite_id}", headers=_as_email(ADMIN_EMAIL))

        session = get_session()
        try:
            count_after = (
                session.query(AdminAuditEvent)
                .filter(AdminAuditEvent.event_type == EventType.INVITE_REVOKE)
                .count()
            )
        finally:
            session.close()
        assert count_before == count_after


# ---------------------------------------------------------------------------
# GET /admin/audit endpoint
# ---------------------------------------------------------------------------


class TestListEndpoint:

    def test_non_admin_403(self, client: TestClient):
        regular = _seed_user("audit-reg@example.com")
        r = client.get("/admin/audit", headers=_as_email(regular.user_id))
        assert r.status_code == 403

    def test_event_types_endpoint(self, client: TestClient):
        _seed_admin()
        r = client.get("/admin/audit/event-types", headers=_as_email(ADMIN_EMAIL))
        assert r.status_code == 200
        types = r.json()["event_types"]
        assert "user.approve" in types
        assert "invite.revoke" in types

    def test_list_returns_newest_first_with_filter(self, client: TestClient):
        _seed_admin()
        target = _seed_user("lf-target@example.com", status=USER_STATUS_PENDING)
        client.post(
            f"/admin/approvals/{target.id}/approve",
            headers=_as_email(ADMIN_EMAIL),
        )
        # filter to approvals only
        r = client.get(
            "/admin/audit?event_type=user.approve",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["events"]
        assert all(e["event_type"] == "user.approve" for e in body["events"])
        # newest first
        ts = [e["created_at"] for e in body["events"]]
        assert ts == sorted(ts, reverse=True)

    def test_actor_filter_matches_string(self, client: TestClient):
        _seed_admin()
        # generate at least one event
        client.post(
            "/admin/invites",
            headers=_as_email(ADMIN_EMAIL),
            json={"max_uses": 1},
        )
        r = client.get(
            f"/admin/audit?actor={ADMIN_EMAIL}",
            headers=_as_email(ADMIN_EMAIL),
        )
        body = r.json()
        assert body["total"] > 0
        assert all(e["actor_user_id_string"] == ADMIN_EMAIL for e in body["events"])

    def test_invalid_event_type_400(self, client: TestClient):
        _seed_admin()
        r = client.get(
            "/admin/audit?event_type=bogus.thing",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 400

    def test_invalid_since_400(self, client: TestClient):
        _seed_admin()
        r = client.get(
            "/admin/audit?since=not-a-date",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 400

    def test_since_until_window_filters(self, client: TestClient):
        _seed_admin()
        # emit one event so there's something to match
        client.post(
            "/admin/invites",
            headers=_as_email(ADMIN_EMAIL),
            json={"max_uses": 1},
        )
        # 1 minute window in the past — should return zero
        past_start = (datetime.utcnow() - timedelta(days=2)).isoformat()
        past_end = (datetime.utcnow() - timedelta(days=1)).isoformat()
        r = client.get(
            f"/admin/audit?since={past_start}&until={past_end}",
            headers=_as_email(ADMIN_EMAIL),
        )
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_pagination(self, client: TestClient):
        _seed_admin()
        # make a handful of invite create events
        for _ in range(3):
            client.post(
                "/admin/invites",
                headers=_as_email(ADMIN_EMAIL),
                json={"max_uses": 1},
            )
        r1 = client.get(
            "/admin/audit?event_type=invite.create&limit=2&offset=0",
            headers=_as_email(ADMIN_EMAIL),
        )
        r2 = client.get(
            "/admin/audit?event_type=invite.create&limit=2&offset=2",
            headers=_as_email(ADMIN_EMAIL),
        )
        body1 = r1.json()
        body2 = r2.json()
        ids1 = {e["id"] for e in body1["events"]}
        ids2 = {e["id"] for e in body2["events"]}
        # different pages, no overlap
        assert ids1.isdisjoint(ids2)
