"""
Tests for the /admin/* cross-user read endpoints.

Phase B changed the gate from `require_cloudflare_access` (which 401s
unless a CF Access identity is present) to `require_admin`, which:

  * accepts the solo sentinel `__local__` (solo dev keeps working without
    extra setup — the only user IS the operator), and
  * for any real identity, requires a matching User row with role='admin'.

These tests cover the new contract: solo passes, X-User-Id callers without
an admin User row 403, CF Access emails with an admin User row pass, and
the existing cross-user reads still return the right shape.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_ADMIN,
    USER_STATUS_ACTIVE,
    User,
    get_session,
)
from backend.services.auth_security import hash_password

from .conftest import as_user
from .test_user_isolation import _archive_paper, _archive_quiz, _archive_topic


# the email we'll stamp admin-tagged requests with throughout this file
ADMIN_EMAIL = "admin@example.com"


def _as_cf_admin(email: str = ADMIN_EMAIL) -> dict[str, str]:
    """Stamp a request as a Cloudflare Access identity (resolves to email user_id)."""
    return {"Cf-Access-Authenticated-User-Email": email}


def _seed_admin(email: str = ADMIN_EMAIL) -> User:
    """
    Insert an admin User row whose `user_id` defaults to the email so the
    CF Access header path resolves into a matching admin record.
    """
    session = get_session()
    try:
        existing = session.query(User).filter(User.email == email).first()
        if existing is not None:
            session.expunge(existing)
            return existing
        u = User(
            email=email,
            user_id=email,
            password_hash=hash_password("dummy12345"),
            status=USER_STATUS_ACTIVE,
            role=USER_ROLE_ADMIN,
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


# ---------------------------------------------------------------------------
# Gate behavior
# ---------------------------------------------------------------------------


class TestAdminGate:
    def test_solo_caller_passes(self, client):
        """No CF Access header → resolves to __local__ → admin gate allows."""
        resp = client.get("/admin/users")
        assert resp.status_code == 200

    def test_non_admin_x_user_id_caller_403s(self, client, user_a):
        """X-User-Id without an admin User row → 403, not data."""
        resp = client.get("/admin/users", headers=as_user(client, user_a))
        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    def test_cf_access_with_admin_user_row_passes(self, client):
        _seed_admin()
        resp = client.get("/admin/users", headers=_as_cf_admin())
        assert resp.status_code == 200

    def test_cf_access_without_admin_user_row_403s(self, client):
        # no User row for this email at all
        resp = client.get("/admin/users", headers=_as_cf_admin("stranger@example.com"))
        assert resp.status_code == 403

    def test_cf_access_with_non_admin_user_row_403s(self, client):
        # seed a regular (non-admin) user with that email
        session = get_session()
        try:
            session.add(User(
                email="regular@example.com",
                user_id="regular@example.com",
                password_hash=hash_password("dummy12345"),
                status=USER_STATUS_ACTIVE,
                role="user",
                created_at=datetime.utcnow(),
            ))
            session.commit()
        finally:
            session.close()
        resp = client.get("/admin/users", headers=_as_cf_admin("regular@example.com"))
        assert resp.status_code == 403

    def test_whoami_echoes_identity(self, client):
        _seed_admin("grace@example.com")
        resp = client.get("/admin/whoami", headers=_as_cf_admin("grace@example.com"))
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "grace@example.com"


# ---------------------------------------------------------------------------
# Cross-user reads (gate auto-passed via _seed_admin in setup)
# ---------------------------------------------------------------------------


class TestAdminReads:
    @pytest.fixture(autouse=True)
    def _seed(self):
        """Seed the admin row used by every read test below."""
        _seed_admin()

    def test_list_users_includes_every_active_identity(self, client, user_a, user_b):
        _archive_paper(client, user_a, "a", "2401.0001")
        _archive_paper(client, user_b, "b", "2401.0002")
        _archive_quiz(client, user_b)

        resp = client.get("/admin/users", headers=_as_cf_admin()).json()
        user_ids = {u["user_id"] for u in resp["users"]}
        assert user_a in user_ids
        assert user_b in user_ids

        # bob's totals reflect both surfaces (papers + quiz + stats row)
        bob = next(u for u in resp["users"] if u["user_id"] == user_b)
        assert bob["row_counts"].get("archived_papers") == 1
        assert bob["row_counts"].get("archived_quizzes") == 1

    def test_user_stats_returns_other_users_data(self, client, user_a):
        for i in range(3):
            _archive_paper(client, user_a, f"a {i}", f"2401.{i:04d}")
        resp = client.get(f"/admin/users/{user_a}/stats", headers=_as_cf_admin()).json()
        assert resp["lifetime"]["papers_archived"] == 3
        assert resp["current_counts"]["papers"] == 3

    def test_user_stats_404s_for_unknown_user(self, client):
        resp = client.get("/admin/users/ghost@example.com/stats", headers=_as_cf_admin())
        assert resp.status_code == 404

    def test_user_papers_returns_other_users_papers(self, client, user_a, user_b):
        _archive_paper(client, user_a, "alice paper", "2401.0001")
        _archive_paper(client, user_b, "bob paper", "2401.0002")
        resp = client.get(f"/admin/users/{user_a}/papers", headers=_as_cf_admin()).json()
        assert resp["total"] == 1
        assert resp["papers"][0]["title"] == "alice paper"
