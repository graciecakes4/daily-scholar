"""
Tests for server-side versioned tour state (users.tour_state JSON map).

Coverage:
  * tour_state exposed in /auth/me, all KNOWN_TOUR_IDS backfilled to 0
    when the column is empty
  * PUT /auth/tour-completed sets the right key when version is higher
  * PUT /auth/tour-completed takes max() per tour_id — a stale callback
    with a lower version doesn't regress a higher stored value
  * PUT /auth/tour-completed is idempotent on no-op (returns updated=False)
  * Unknown tour_id is rejected with 400
  * PUT /auth/tour-reset clears every key
  * Both endpoints require an active in-app session (401/403)
  * Bumping one tour doesn't affect the others (independent)
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.api.auth import KNOWN_TOUR_IDS
from backend.database import (
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
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
    tour_state: dict | None = None,
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
            tour_state=tour_state if tour_state is not None else {},
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
# /auth/me exposes the tour_state map
# ---------------------------------------------------------------------------


class TestAuthMeExposesTourState:

    def test_fresh_user_backfills_all_known_ids_to_zero(self, client: TestClient):
        u = _seed_user("ame-fresh@example.com")
        _login(client, u.email)
        r = client.get("/auth/me")
        assert r.status_code == 200
        state = r.json()["profile"]["tour_state"]
        # every known tour id present even though the DB row is empty
        for tid in KNOWN_TOUR_IDS:
            assert state[tid] == 0
        client.cookies.clear()

    def test_existing_value_returned_and_unknown_keys_in_db_preserved(self, client: TestClient):
        u = _seed_user(
            "ame-mixed@example.com",
            tour_state={"dashboard": 2, "future_tour": 5},
        )
        _login(client, u.email)
        state = client.get("/auth/me").json()["profile"]["tour_state"]
        # the known dashboard value comes through
        assert state["dashboard"] == 2
        # other known ids are backfilled
        assert state["scope"] == 0
        assert state["topics"] == 0
        # unknown keys in the DB don't crash; they're just included
        assert state.get("future_tour") == 5
        client.cookies.clear()


# ---------------------------------------------------------------------------
# PUT /auth/tour-completed
# ---------------------------------------------------------------------------


class TestTourCompletedEndpoint:

    def test_bumps_per_tour_independently(self, client: TestClient):
        u = _seed_user("tc-indep@example.com")
        _login(client, u.email)

        # bump dashboard
        r = client.put("/auth/tour-completed", json={"tour_id": "dashboard", "version": 2})
        assert r.status_code == 200
        assert r.json()["tour_id"] == "dashboard"
        assert r.json()["version"] == 2
        assert r.json()["updated"] is True

        # bump topics — dashboard stays put
        r = client.put("/auth/tour-completed", json={"tour_id": "topics", "version": 3})
        assert r.status_code == 200

        state = client.get("/auth/me").json()["profile"]["tour_state"]
        assert state["dashboard"] == 2
        assert state["topics"] == 3
        assert state["scope"] == 0     # untouched
        client.cookies.clear()

    def test_idempotent_on_same_version(self, client: TestClient):
        u = _seed_user("tc-same@example.com", tour_state={"scope": 2})
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"tour_id": "scope", "version": 2})
        assert r.status_code == 200
        assert r.json()["updated"] is False
        client.cookies.clear()

    def test_does_not_regress_with_lower_version(self, client: TestClient):
        """
        Stale callback from an older tab (TOUR_VERSION=1) shouldn't undo
        the newer tab's commit (TOUR_VERSION=2).
        """
        u = _seed_user("tc-stale@example.com", tour_state={"dashboard": 2})
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"tour_id": "dashboard", "version": 1})
        assert r.status_code == 200
        assert r.json()["version"] == 2
        assert r.json()["updated"] is False
        # DB also unchanged
        session = get_session()
        try:
            row = session.query(User).filter(User.id == u.id).first()
            assert row.tour_state["dashboard"] == 2
        finally:
            session.close()
        client.cookies.clear()

    def test_unknown_tour_id_400(self, client: TestClient):
        u = _seed_user("tc-unknown@example.com")
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"tour_id": "bogus", "version": 1})
        assert r.status_code == 400
        assert "unknown tour_id" in r.json()["detail"].lower()
        client.cookies.clear()

    def test_version_must_be_positive(self, client: TestClient):
        u = _seed_user("tc-zero@example.com")
        _login(client, u.email)
        # pydantic ge=1 → 422
        r = client.put("/auth/tour-completed", json={"tour_id": "dashboard", "version": 0})
        assert r.status_code == 422
        client.cookies.clear()

    def test_no_cookie_401(self, client: TestClient):
        r = client.put("/auth/tour-completed", json={"tour_id": "dashboard", "version": 1})
        assert r.status_code == 401

    def test_pending_user_403(self, client: TestClient):
        u = _seed_user("tc-pending@example.com", status=USER_STATUS_PENDING)
        _login(client, u.email)
        r = client.put("/auth/tour-completed", json={"tour_id": "dashboard", "version": 1})
        assert r.status_code == 403
        client.cookies.clear()


# ---------------------------------------------------------------------------
# PUT /auth/tour-reset
# ---------------------------------------------------------------------------


class TestTourResetEndpoint:

    def test_clears_every_key(self, client: TestClient):
        u = _seed_user(
            "tr-clear@example.com",
            tour_state={"dashboard": 5, "scope": 3, "topics": 2, "future": 9},
        )
        _login(client, u.email)
        r = client.put("/auth/tour-reset")
        assert r.status_code == 200
        assert r.json()["tour_state"] == {}

        # /auth/me re-backfills known ids to 0 from the empty dict
        state = client.get("/auth/me").json()["profile"]["tour_state"]
        for tid in KNOWN_TOUR_IDS:
            assert state[tid] == 0
        # the "future" key is gone too (full clear)
        assert "future" not in state
        client.cookies.clear()

    def test_idempotent_when_already_empty(self, client: TestClient):
        u = _seed_user("tr-empty@example.com")
        _login(client, u.email)
        r = client.put("/auth/tour-reset")
        assert r.status_code == 200
        assert r.json()["tour_state"] == {}
        client.cookies.clear()

    def test_no_cookie_401(self, client: TestClient):
        r = client.put("/auth/tour-reset")
        assert r.status_code == 401

    def test_per_tour_reset_clears_only_that_key(self, client: TestClient):
        # arrange: a user with all three tours marked seen
        u = _seed_user(
            "tr-one@example.com",
            tour_state={"dashboard": 4, "scope": 2, "topics": 3},
        )
        _login(client, u.email)

        # act: reset just the dashboard tour
        r = client.put("/auth/tour-reset?tour_id=dashboard")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        # the response carries the new state dict
        assert body["tour_state"]["dashboard"] == 0
        assert body["tour_state"]["scope"] == 2
        assert body["tour_state"]["topics"] == 3

        # /auth/me agrees
        state = client.get("/auth/me").json()["profile"]["tour_state"]
        assert state["dashboard"] == 0
        assert state["scope"] == 2
        assert state["topics"] == 3
        client.cookies.clear()

    def test_per_tour_reset_unknown_id_400(self, client: TestClient):
        u = _seed_user("tr-bogus@example.com", tour_state={"dashboard": 2})
        _login(client, u.email)
        r = client.put("/auth/tour-reset?tour_id=bogus")
        assert r.status_code == 400
        assert "unknown tour_id" in r.json()["detail"].lower()
        # state must be untouched on a 400
        state = client.get("/auth/me").json()["profile"]["tour_state"]
        assert state["dashboard"] == 2
        client.cookies.clear()
