"""
Tests for Phase B: invite-code lifecycle + admin approval queue.

Coverage:
  * invite_codes service: generate, validate_and_redeem (all failure
    reasons), revoke, list filters
  * /admin/invites endpoints: create / list / revoke, role gate
  * /admin/approvals endpoints: list pending, approve flips status +
    stamps audit fields, reject deletes user + side rows
  * /auth/signup gate behavior with and without OPEN_SIGNUP
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
    InviteCode,
    User,
    UserSettings,
    UserStats,
    get_session,
)
from backend.services.auth_security import hash_password
from backend.services.invite_codes import (
    InviteCodeExhausted,
    InviteCodeExpired,
    InviteCodeRevoked,
    InviteCodeUnknown,
    generate_invite_code,
    list_invite_codes,
    revoke_invite_code,
    validate_and_redeem,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers — admin user seeding (Phase B's role gate needs a real admin row
# when the test goes through a CF Access header instead of solo)
# ---------------------------------------------------------------------------


ADMIN_EMAIL = "admin@example.com"


def _seed_admin(email: str = ADMIN_EMAIL) -> User:
    session = get_session()
    try:
        existing = session.query(User).filter(User.email == email).first()
        if existing is not None:
            session.expunge(existing)
            return existing
        u = User(
            email=email, user_id=email,
            password_hash=hash_password("dummy12345"),
            status=USER_STATUS_ACTIVE, role=USER_ROLE_ADMIN,
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


def _seed_pending_user(email: str, user_id: str | None = None) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=(user_id or email).lower(),
            password_hash=hash_password("supersecret123"),
            status=USER_STATUS_PENDING, role=USER_ROLE_USER,
            created_at=datetime.utcnow(),
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        session.expunge(u)
        return u
    finally:
        session.close()


def _as_admin() -> dict[str, str]:
    return {"Cf-Access-Authenticated-User-Email": ADMIN_EMAIL}


# ---------------------------------------------------------------------------
# Service: invite_codes module
# ---------------------------------------------------------------------------


class TestInviteCodeService:

    def test_generate_returns_unique_short_code(self):
        admin = _seed_admin()
        a = generate_invite_code(admin.id)
        b = generate_invite_code(admin.id)
        assert a.code != b.code
        # urlsafe(9) → 12 chars
        assert len(a.code) == 12

    def test_generate_rejects_zero_max_uses(self):
        admin = _seed_admin()
        with pytest.raises(ValueError):
            generate_invite_code(admin.id, max_uses=0)

    def test_redeem_increments_uses(self):
        admin = _seed_admin()
        user = _seed_pending_user("redeemer@example.com")
        code = generate_invite_code(admin.id)
        result = validate_and_redeem(code.code, redeeming_user_id_int=user.id)
        assert result.uses == 1
        assert result.max_uses == 1

    def test_redeem_unknown_raises(self):
        user = _seed_pending_user("unk@example.com")
        with pytest.raises(InviteCodeUnknown):
            validate_and_redeem("nope-not-a-real-code", redeeming_user_id_int=user.id)

    def test_redeem_revoked_raises(self):
        admin = _seed_admin()
        user = _seed_pending_user("rev@example.com")
        code = generate_invite_code(admin.id)
        revoke_invite_code(code.id)
        with pytest.raises(InviteCodeRevoked):
            validate_and_redeem(code.code, redeeming_user_id_int=user.id)

    def test_redeem_expired_raises(self):
        admin = _seed_admin()
        user = _seed_pending_user("exp@example.com")
        code = generate_invite_code(
            admin.id,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        with pytest.raises(InviteCodeExpired):
            validate_and_redeem(code.code, redeeming_user_id_int=user.id)

    def test_redeem_exhausted_raises(self):
        admin = _seed_admin()
        u1 = _seed_pending_user("ex1@example.com")
        u2 = _seed_pending_user("ex2@example.com")
        code = generate_invite_code(admin.id, max_uses=1)
        # first redeem succeeds
        validate_and_redeem(code.code, redeeming_user_id_int=u1.id)
        # second exhausts
        with pytest.raises(InviteCodeExhausted):
            validate_and_redeem(code.code, redeeming_user_id_int=u2.id)

    def test_multi_use_code_allows_max_uses_redemptions(self):
        admin = _seed_admin()
        code = generate_invite_code(admin.id, max_uses=3)
        for i in range(3):
            user = _seed_pending_user(f"multi{i}@example.com")
            r = validate_and_redeem(code.code, redeeming_user_id_int=user.id)
            assert r.uses == i + 1
        # fourth fails
        u_extra = _seed_pending_user("extra@example.com")
        with pytest.raises(InviteCodeExhausted):
            validate_and_redeem(code.code, redeeming_user_id_int=u_extra.id)

    def test_revoke_is_idempotent(self):
        admin = _seed_admin()
        code = generate_invite_code(admin.id)
        assert revoke_invite_code(code.id) is True
        # second time: already revoked
        assert revoke_invite_code(code.id) is False
        # unknown id
        assert revoke_invite_code(999999) is False

    def test_list_filters_revoked(self):
        admin = _seed_admin()
        a = generate_invite_code(admin.id)
        b = generate_invite_code(admin.id)
        revoke_invite_code(a.id)
        all_rows = list_invite_codes(include_revoked=True)
        all_ids = {r.id for r in all_rows}
        assert a.id in all_ids and b.id in all_ids
        active_rows = list_invite_codes(include_revoked=False)
        active_ids = {r.id for r in active_rows}
        assert a.id not in active_ids
        assert b.id in active_ids


# ---------------------------------------------------------------------------
# /admin/invites endpoints
# ---------------------------------------------------------------------------


class TestAdminInvitesEndpoints:

    def test_create_invite_requires_admin(self, client: TestClient, user_a):
        # non-admin → 403
        r = client.post(
            "/admin/invites", json={"max_uses": 1},
            headers={"Cf-Access-Authenticated-User-Email": user_a},
        )
        assert r.status_code == 403

    def test_admin_can_create_list_and_revoke(self, client: TestClient):
        _seed_admin()
        # create
        r = client.post(
            "/admin/invites", json={"expires_in_days": 7, "max_uses": 5},
            headers=_as_admin(),
        )
        assert r.status_code == 201
        inv = r.json()["invite"]
        assert inv["state"] == "available"
        assert inv["max_uses"] == 5
        # list shows it
        r2 = client.get("/admin/invites", headers=_as_admin())
        assert r2.status_code == 200
        assert any(x["id"] == inv["id"] for x in r2.json()["invites"])
        # revoke
        r3 = client.delete(f"/admin/invites/{inv['id']}", headers=_as_admin())
        assert r3.status_code == 200
        assert r3.json()["revoked"] is True
        # second revoke is idempotent
        r4 = client.delete(f"/admin/invites/{inv['id']}", headers=_as_admin())
        assert r4.status_code == 200
        assert r4.json()["revoked"] is False

    def test_solo_mode_cannot_create_invite(self, client: TestClient):
        # solo dev passes the admin gate (__local__ = admin) but the
        # create endpoint refuses with a clear message
        r = client.post("/admin/invites", json={"max_uses": 1})
        assert r.status_code == 400
        assert "solo mode" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /auth/signup gate behavior
# ---------------------------------------------------------------------------


class TestSignupGate:

    def test_signup_without_code_fails_when_gate_on(
        self, client: TestClient, monkeypatch,
    ):
        # turn the gate ON for this test
        monkeypatch.setenv("OPEN_SIGNUP", "0")
        r = client.post("/auth/signup", json={
            "email": "gated1@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 400
        assert "invite" in r.json()["detail"].lower()

    def test_signup_with_valid_code_succeeds_when_gate_on(
        self, client: TestClient, monkeypatch,
    ):
        admin = _seed_admin()
        code = generate_invite_code(admin.id)
        monkeypatch.setenv("OPEN_SIGNUP", "0")
        r = client.post("/auth/signup", json={
            "email": "gated2@example.com",
            "password": "supersecret123",
            "invite_code": code.code,
        })
        assert r.status_code == 201

        # the code should now be marked used
        session = get_session()
        try:
            row = session.query(InviteCode).filter(InviteCode.id == code.id).first()
            assert row.uses == 1
        finally:
            session.close()

    def test_signup_with_revoked_code_fails(
        self, client: TestClient, monkeypatch,
    ):
        admin = _seed_admin()
        code = generate_invite_code(admin.id)
        revoke_invite_code(code.id)
        monkeypatch.setenv("OPEN_SIGNUP", "0")
        r = client.post("/auth/signup", json={
            "email": "gated3@example.com",
            "password": "supersecret123",
            "invite_code": code.code,
        })
        assert r.status_code == 400
        assert "revoked" in r.json()["detail"].lower()

    def test_failed_signup_does_not_burn_code(
        self, client: TestClient, monkeypatch,
    ):
        """If the user insert fails (duplicate email), the invite's
        `uses` should NOT be incremented — the transaction rolls back."""
        admin = _seed_admin()
        _seed_pending_user("dup@example.com")        # email already taken
        code = generate_invite_code(admin.id)
        monkeypatch.setenv("OPEN_SIGNUP", "0")
        r = client.post("/auth/signup", json={
            "email": "dup@example.com",
            "password": "supersecret123",
            "invite_code": code.code,
        })
        assert r.status_code == 409          # duplicate email
        # code still available
        session = get_session()
        try:
            row = session.query(InviteCode).filter(InviteCode.id == code.id).first()
            assert row.uses == 0
        finally:
            session.close()

    def test_open_signup_skips_invite_check(self, client: TestClient):
        # conftest sets OPEN_SIGNUP=1 by default; no invite_code needed
        r = client.post("/auth/signup", json={
            "email": "open@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# /admin/approvals endpoints
# ---------------------------------------------------------------------------


class TestApprovalsEndpoints:

    def test_list_pending_returns_oldest_first(self, client: TestClient):
        _seed_admin()
        _seed_pending_user("first@example.com")
        _seed_pending_user("second@example.com")
        r = client.get("/admin/approvals", headers=_as_admin())
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 2
        emails = [p["email"] for p in body["pending"]]
        # admin (created earlier in fixture) is active not pending, so
        # not in the list; first should appear before second
        assert emails.index("first@example.com") < emails.index("second@example.com")
        assert "admin@example.com" not in emails

    def test_approve_flips_status_and_stamps_audit(self, client: TestClient):
        _seed_admin()
        target = _seed_pending_user("toapprove@example.com")
        r = client.post(
            f"/admin/approvals/{target.id}/approve",
            headers=_as_admin(),
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        session = get_session()
        try:
            row = session.query(User).filter(User.id == target.id).first()
            assert row.status == USER_STATUS_ACTIVE
            assert row.approved_at is not None
            # admin user_id resolved to its id and stamped
            assert row.approved_by_user_id is not None
        finally:
            session.close()

    def test_approve_idempotent_on_active_user(self, client: TestClient):
        _seed_admin()
        target = _seed_pending_user("idem@example.com")
        client.post(f"/admin/approvals/{target.id}/approve", headers=_as_admin())
        # second approve is a success no-op
        r = client.post(f"/admin/approvals/{target.id}/approve", headers=_as_admin())
        assert r.status_code == 200
        assert "already" in r.json()["message"].lower()

    def test_approve_unknown_user_404s(self, client: TestClient):
        _seed_admin()
        r = client.post("/admin/approvals/999999/approve", headers=_as_admin())
        assert r.status_code == 404

    def test_reject_deletes_user_and_side_rows(self, client: TestClient):
        _seed_admin()
        target = _seed_pending_user("reject@example.com", user_id="rejectee")
        # seed a settings row + stats row to confirm they get cleaned up
        session = get_session()
        try:
            session.add(UserSettings(user_id="rejectee", scope_mode="all", scope_topic_ids=[]))
            session.add(UserStats(user_id="rejectee"))
            session.commit()
        finally:
            session.close()

        r = client.post(f"/admin/approvals/{target.id}/reject", headers=_as_admin())
        assert r.status_code == 200
        assert r.json()["deleted_user_id"] == "rejectee"

        session = get_session()
        try:
            assert session.query(User).filter(User.id == target.id).first() is None
            assert session.query(UserSettings).filter(UserSettings.user_id == "rejectee").first() is None
            assert session.query(UserStats).filter(UserStats.user_id == "rejectee").first() is None
        finally:
            session.close()

    def test_reject_refuses_to_delete_active_user(self, client: TestClient):
        _seed_admin()
        target = _seed_pending_user("active@example.com")
        # approve first
        client.post(f"/admin/approvals/{target.id}/approve", headers=_as_admin())
        # now reject is refused
        r = client.post(f"/admin/approvals/{target.id}/reject", headers=_as_admin())
        assert r.status_code == 400
        assert "active" in r.json()["detail"].lower()
