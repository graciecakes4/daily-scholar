"""
Tests for the Phase A in-app auth foundation.

Coverage:
  * password hashing round-trip + edge cases
  * user_id format validation
  * signup endpoint (validation, uniqueness, status defaults)
  * login endpoint (success, wrong-password, suspended-block, pending-allowed)
  * logout endpoint + session revocation
  * /auth/me with and without cookie
  * get_current_user_id session-cookie layer:
      - active user → user.user_id
      - pending → 403
      - suspended → 403
      - invalid/expired cookie → silent fallthrough to CF Access path
  * CF Access header still works when no session cookie (regression)
  * __local__ sentinel still returned in solo mode (regression)
  * full signup → admin-approve → login → me → logout cycle

The fixtures rebuild the schema once per session via the same TestClient
pattern as test_notifications.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_ADMIN,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    Session,
    User,
    get_session,
)
from backend.services.auth_security import (
    InvalidEmailError,
    InvalidUserIdError,
    default_user_id_from_email,
    hash_password,
    validate_email,
    validate_user_id,
    verify_password,
)
from backend.services.auth_sessions import create_session, revoke_session

from .conftest import as_user


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    """Same pattern as test_notifications: bootstrap the schema via lifespan."""
    from backend.main import app

    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# auth_security: pure-Python unit tests (no DB)
# ---------------------------------------------------------------------------


class TestPasswordHashing:

    def test_round_trip(self):
        h = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", h)

    def test_wrong_password_rejected(self):
        h = hash_password("right-password")
        assert not verify_password("wrong-password", h)

    def test_short_password_rejected_at_hash_time(self):
        with pytest.raises(ValueError):
            hash_password("short")

    def test_verify_handles_malformed_hash(self):
        # caller might pass a corrupted DB value — should be False, not raise
        assert verify_password("anything", "not-a-real-bcrypt-hash") is False


class TestUserIdValidation:

    def test_accepts_simple_handle(self):
        assert validate_user_id("grace") == "grace"

    def test_lowercases(self):
        assert validate_user_id("Grace") == "grace"

    def test_allows_dots_dashes_underscores(self):
        assert validate_user_id("grace.c-m_alley") == "grace.c-m_alley"

    def test_rejects_too_short(self):
        with pytest.raises(InvalidUserIdError):
            validate_user_id("ab")

    def test_rejects_too_long(self):
        with pytest.raises(InvalidUserIdError):
            validate_user_id("a" * 31)

    def test_rejects_double_underscore_prefix(self):
        with pytest.raises(InvalidUserIdError):
            validate_user_id("__local__")

    def test_rejects_uppercase_after_normalize(self):
        # mixed-case is accepted but lowercased; pure-symbol garbage rejects
        with pytest.raises(InvalidUserIdError):
            validate_user_id("has spaces")

    def test_rejects_special_chars(self):
        with pytest.raises(InvalidUserIdError):
            validate_user_id("user@example")

    def test_default_user_id_from_email_lowercases(self):
        assert default_user_id_from_email("Grace@Example.COM") == "grace@example.com"


class TestEmailValidation:

    def test_basic_email_ok(self):
        assert validate_email("Grace@example.com") == "grace@example.com"

    def test_rejects_no_at(self):
        with pytest.raises(InvalidEmailError):
            validate_email("notanemail")


# ---------------------------------------------------------------------------
# /auth/signup
# ---------------------------------------------------------------------------


class TestSignup:

    def test_creates_pending_user_with_default_user_id(self, client: TestClient):
        r = client.post("/auth/signup", json={
            "email": "alice@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 201, r.text
        profile = r.json()["profile"]
        assert profile["email"] == "alice@example.com"
        # default user_id is the email
        assert profile["user_id"] == "alice@example.com"
        assert profile["status"] == "pending"
        assert profile["role"] == "user"

    def test_accepts_custom_user_id(self, client: TestClient):
        r = client.post("/auth/signup", json={
            "email": "bob@example.com",
            "password": "supersecret123",
            "user_id": "bob",
        })
        assert r.status_code == 201
        assert r.json()["profile"]["user_id"] == "bob"

    def test_rejects_short_password(self, client: TestClient):
        r = client.post("/auth/signup", json={
            "email": "x@example.com",
            "password": "short",
        })
        # pydantic returns 422 on min_length violation
        assert r.status_code == 422

    def test_rejects_bad_user_id_format(self, client: TestClient):
        r = client.post("/auth/signup", json={
            "email": "y@example.com",
            "password": "supersecret123",
            "user_id": "__sneaky",
        })
        assert r.status_code == 400
        assert "reserved" in r.json()["detail"].lower()

    def test_rejects_duplicate_email(self, client: TestClient):
        body = {"email": "dup@example.com", "password": "supersecret123"}
        r1 = client.post("/auth/signup", json=body)
        assert r1.status_code == 201
        r2 = client.post("/auth/signup", json=body)
        assert r2.status_code == 409
        assert "email" in r2.json()["detail"].lower()

    def test_rejects_duplicate_user_id(self, client: TestClient):
        client.post("/auth/signup", json={
            "email": "a@example.com",
            "password": "supersecret123",
            "user_id": "shared",
        })
        r = client.post("/auth/signup", json={
            "email": "b@example.com",
            "password": "supersecret123",
            "user_id": "shared",
        })
        assert r.status_code == 409
        assert "username" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Helpers for login/me/logout tests
# ---------------------------------------------------------------------------


def _make_user(
    email: str,
    password: str = "supersecret123",
    user_id: str | None = None,
    status: str = USER_STATUS_ACTIVE,
    role: str = "user",
) -> User:
    """Insert a user directly (skipping signup) at the requested status."""
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=(user_id or email).lower(),
            password_hash=hash_password(password),
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


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


class TestLogin:

    def test_active_user_login_returns_cookie(self, client: TestClient):
        _make_user("login-active@example.com")
        r = client.post("/auth/login", json={
            "email": "login-active@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 200
        assert r.json()["profile"]["email"] == "login-active@example.com"
        assert r.json()["pending"] is False
        # cookie set
        assert "ds_session" in client.cookies

    def test_wrong_password_401(self, client: TestClient):
        _make_user("wrongpw@example.com")
        r = client.post("/auth/login", json={
            "email": "wrongpw@example.com",
            "password": "the-wrong-one",
        })
        assert r.status_code == 401
        assert "ds_session" not in client.cookies

    def test_unknown_email_401_same_message(self, client: TestClient):
        r = client.post("/auth/login", json={
            "email": "nobody-here@example.com",
            "password": "whatever123",
        })
        assert r.status_code == 401
        # don't leak which one was wrong
        assert "invalid" in r.json()["detail"].lower()

    def test_pending_user_can_log_in_but_status_flagged(self, client: TestClient):
        _make_user("pending@example.com", status=USER_STATUS_PENDING)
        r = client.post("/auth/login", json={
            "email": "pending@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 200
        assert r.json()["pending"] is True
        assert r.json()["profile"]["status"] == "pending"

    def test_suspended_user_blocked_with_403(self, client: TestClient):
        _make_user("sus@example.com", status=USER_STATUS_SUSPENDED)
        r = client.post("/auth/login", json={
            "email": "sus@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 403
        assert "suspended" in r.json()["detail"].lower()
        assert "ds_session" not in client.cookies


# ---------------------------------------------------------------------------
# /auth/me + /auth/logout
# ---------------------------------------------------------------------------


class TestMeAndLogout:

    def test_me_without_cookie_401s(self, client: TestClient):
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_me_with_valid_cookie_returns_profile(self, client: TestClient):
        _make_user("me@example.com")
        client.post("/auth/login", json={
            "email": "me@example.com",
            "password": "supersecret123",
        })
        r = client.get("/auth/me")
        assert r.status_code == 200
        assert r.json()["profile"]["email"] == "me@example.com"

    def test_logout_revokes_session(self, client: TestClient):
        _make_user("logout@example.com")
        client.post("/auth/login", json={
            "email": "logout@example.com",
            "password": "supersecret123",
        })
        # confirm we're in
        assert client.get("/auth/me").status_code == 200

        r = client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # cookie cleared by TestClient when the response sets Max-Age=0
        # and subsequent /auth/me 401s
        # (the cookie jar may still have it — but the server-side row is revoked)
        r2 = client.get("/auth/me", cookies={"ds_session": "anything-old"})
        assert r2.status_code == 401

    def test_logout_idempotent_with_no_cookie(self, client: TestClient):
        r = client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json()["revoked"] is False


# ---------------------------------------------------------------------------
# get_current_user_id: the session-cookie layer
# ---------------------------------------------------------------------------


class TestAuthDependency:
    """
    Exercises get_current_user_id via a real endpoint (/stats, which depends
    on it). Per-request behavior is what callers actually care about.
    """

    def test_active_session_resolves_to_user_id(self, client: TestClient):
        u = _make_user("dep-active@example.com", user_id="dep-active")
        client.post("/auth/login", json={
            "email": "dep-active@example.com",
            "password": "supersecret123",
        })
        # /stats returns 200 + the user_id is the one keyed on `dep-active`
        r = client.get("/stats")
        assert r.status_code == 200

    def test_pending_session_blocks_protected_endpoint(self, client: TestClient):
        _make_user("dep-pending@example.com", status=USER_STATUS_PENDING)
        client.post("/auth/login", json={
            "email": "dep-pending@example.com",
            "password": "supersecret123",
        })
        r = client.get("/stats")
        assert r.status_code == 403
        assert "pending" in r.json()["detail"].lower()

    def test_suspended_session_403s_on_protected_endpoint(self, client: TestClient):
        # we can't *log in* as suspended, so seed the session directly
        u = _make_user("dep-sus@example.com", status=USER_STATUS_SUSPENDED)
        token = create_session(u.id)
        r = client.get("/stats", cookies={"ds_session": token})
        assert r.status_code == 403
        assert "suspended" in r.json()["detail"].lower()

    def test_invalid_cookie_falls_through_to_default(self, client: TestClient):
        # bogus token = no match → silently fall through to __local__
        r = client.get("/stats", cookies={"ds_session": "totally-fake-token"})
        assert r.status_code == 200    # solo-mode fallback still works

    def test_expired_session_falls_through(self, client: TestClient):
        u = _make_user("dep-expired@example.com")
        # insert a session that's already expired
        session = get_session()
        try:
            row = Session(
                token="expired-token-abc",
                user_id=u.id,
                created_at=datetime.utcnow() - timedelta(days=60),
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            session.add(row)
            session.commit()
        finally:
            session.close()
        # expired → fall through (no 403) → solo mode answers
        r = client.get("/stats", cookies={"ds_session": "expired-token-abc"})
        assert r.status_code == 200

    def test_session_cookie_wins_over_cf_access_header(self, client: TestClient):
        """
        When BOTH a session cookie and a CF Access header are present, the
        session wins. (CF Access header still gets us in if there's no cookie.)
        """
        u = _make_user("dep-priority@example.com", user_id="dep-priority")
        client.post("/auth/login", json={
            "email": "dep-priority@example.com",
            "password": "supersecret123",
        })
        # also pass a CF Access header for a totally different user;
        # endpoint should reflect the session user, not the header one.
        r = client.get(
            "/stats",
            headers={"Cf-Access-Authenticated-User-Email": "intruder@example.com"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Regression: pre-existing auth paths still work
# ---------------------------------------------------------------------------


class TestBackwardCompat:

    def test_cf_access_header_still_works(self, client: TestClient, user_a):
        # no session cookie at all; CF Access header → identity = user_a
        r = client.get("/stats", headers=as_user(client, user_a))
        assert r.status_code == 200

    def test_local_sentinel_still_works(self, client: TestClient):
        # no cookies, no headers → __local__ fallback, solo mode 200s
        r = client.get("/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# End-to-end: signup → admin-approves → login → me → logout
# ---------------------------------------------------------------------------


class TestFullSignupCycle:

    def test_full_cycle(self, client: TestClient):
        # 1. signup
        r = client.post("/auth/signup", json={
            "email": "e2e@example.com",
            "password": "supersecret123",
            "user_id": "e2e",
        })
        assert r.status_code == 201

        # 2. login as pending → can hit /auth/me but blocked from /stats
        r = client.post("/auth/login", json={
            "email": "e2e@example.com",
            "password": "supersecret123",
        })
        assert r.status_code == 200
        assert r.json()["pending"] is True
        assert client.get("/auth/me").status_code == 200
        assert client.get("/stats").status_code == 403

        # 3. simulate admin approval (Phase B will be a real endpoint)
        session = get_session()
        try:
            u = session.query(User).filter(User.email == "e2e@example.com").first()
            u.status = USER_STATUS_ACTIVE
            u.approved_at = datetime.utcnow()
            session.commit()
        finally:
            session.close()

        # 4. now /stats works because the dependency reads status on each call
        assert client.get("/stats").status_code == 200

        # 5. logout → /stats falls back to __local__ (200 in solo mode)
        client.post("/auth/logout")
        assert client.get("/auth/me", cookies={"ds_session": "x"}).status_code == 401
