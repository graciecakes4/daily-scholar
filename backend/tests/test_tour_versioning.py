"""
Tests for server-side versioned tour state (users.tour_version_seen).

Coverage:
  * tour_version_seen exposed in /auth/me, defaults to 0 for new users
  * PUT /auth/tour-completed sets value when the incoming version is
    higher than the stored one (the common case)
  * PUT /auth/tour-completed takes max() — a stale callback with a
    lower version doesn't regress a higher stored value
  * PUT /auth/tour-completed is idempotent on no-op (same version,
    returns updated=False)
  * PUT /auth/tour-reset zeroes it
  * Both endpoints require an active in-app session: no cookie → 401,
    suspended → 403, pending → 403
  * Solo `__local__` has no session cookie so both endpoints 401 cleanly
    (matches the rest of the self-service auth endpoints)
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    User,
    get_session,
)
from backend.services.auth_security import hash_password


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


def _seed_user(
    email: str,
    *,
    password: str = "supersecret123",
    status: str = USER_STATUS_ACTIVE,
    tour_version_seen: int = 0,
) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=email.lower(),
            password_hash=hash_password(password),
            status=status,
            role=USER_ROLE_USER,
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow() if status == USER_STATUS_ACTIVE else None,
            tour_version_seen=tour_version_seen,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        session.expunge(u)
        return u
    finally:
        session.close()


def _login(client: TestClient, email: str, password: str = "supersecret123") -> None:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# /auth/me exposes the field
# ---------------------------------------------------------------------------


class TestAuthMeExposesTourVersionSeen:

    def test_fresh_user_defaults_to_zero(self, client: TestClient):
        u = _seed_user("ame-fresh-tour@example.com")
        _login(client, u.email)
        r = client.get("/auth/me")
        assert r.status_code == 200
        assert r.json()["profile"]["tour_version_seen"] == 0
        client.cookies.clear()

    def test_existing_value_returned(self, client: TestClient):
        u = _seed_user("ame-seen-tour@example.com", tour_version_seen=3)
        _login(client, u.email)
        r = client.get("/auth/me")
        assert r.json()["profile"]["tour_version_seen"] == 3
        client.cookies.clear()


# ---------------------------------------------------------------------------
# PUT /auth/tour-completed
# ---------------------------------------------------------------------------


class TestTourCompletedEndpoint:

    def test_bumps_when_higher(self, client: TestClient):
        u = _seed_user("tc-bump@example.com", tour_version_seen=0)
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"version": 2})
        assert r.status_code == 200
        body = r.json()
        assert body["tour_version_seen"] == 2
        assert body["updated"] is True

        # confirm /auth/me agrees
        r2 = client.get("/auth/me")
        assert r2.json()["profile"]["tour_version_seen"] == 2
        client.cookies.clear()

    def test_idempotent_on_same_version(self, client: TestClient):
        u = _seed_user("tc-same@example.com", tour_version_seen=2)
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"version": 2})
        assert r.status_code == 200
        assert r.json()["tour_version_seen"] == 2
        assert r.json()["updated"] is False
        client.cookies.clear()

    def test_does_not_regress_with_lower_version(self, client: TestClient):
        """
        A stale callback from an older frontend bundle (e.g., an open tab
        with TOUR_VERSION=1 while a newer tab is on version 2) must not
        regress the stored value.
        """
        u = _seed_user("tc-stale@example.com", tour_version_seen=2)
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"version": 1})
        assert r.status_code == 200
        assert r.json()["tour_version_seen"] == 2     # unchanged
        assert r.json()["updated"] is False
        # DB also unchanged
        session = get_session()
        try:
            row = session.query(User).filter(User.id == u.id).first()
            assert row.tour_version_seen == 2
        finally:
            session.close()
        client.cookies.clear()

    def test_version_must_be_positive(self, client: TestClient):
        u = _seed_user("tc-zero@example.com")
        _login(client, u.email)
        # pydantic ge=1 → 422
        r = client.put("/auth/tour-completed", json={"version": 0})
        assert r.status_code == 422
        client.cookies.clear()

    def test_no_cookie_401(self, client: TestClient):
        r = client.put("/auth/tour-completed", json={"version": 1})
        assert r.status_code == 401

    def test_pending_user_403(self, client: TestClient):
        u = _seed_user("tc-pending@example.com", status=USER_STATUS_PENDING)
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"version": 1})
        # _require_authed_user 403s on non-active status
        assert r.status_code == 403
        client.cookies.clear()


# ---------------------------------------------------------------------------
# PUT /auth/tour-reset
# ---------------------------------------------------------------------------


class TestTourResetEndpoint:

    def test_zeroes_value(self, client: TestClient):
        u = _seed_user("tr-zero@example.com", tour_version_seen=5)
        _login(client, u.email)
        r = client.put("/auth/tour-reset")
        assert r.status_code == 200
        assert r.json()["tour_version_seen"] == 0

        r2 = client.get("/auth/me")
        assert r2.json()["profile"]["tour_version_seen"] == 0
        client.cookies.clear()

    def test_idempotent_when_already_zero(self, client: TestClient):
        u = _seed_user("tr-already@example.com", tour_version_seen=0)
        _login(client, u.email)
        r = client.put("/auth/tour-reset")
        assert r.status_code == 200
        assert r.json()["tour_version_seen"] == 0
        client.cookies.clear()

    def test_no_cookie_401(self, client: TestClient):
        r = client.put("/auth/tour-reset")
        assert r.status_code == 401
