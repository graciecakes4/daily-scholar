"""
Tests for the /admin/* cross-user read endpoints.

Two things matter:
  1. They're protected by `require_cloudflare_access` — solo / X-User-Id
     callers should 401, not get data.
  2. When the caller IS a CF Access identity, they can read any user's
     data without per-user-id restrictions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import as_user
from .test_user_isolation import _archive_paper, _archive_quiz, _archive_topic


def _as_cf_admin(email: str = "admin@example.com") -> dict[str, str]:
    """Stamp a request as a Cloudflare Access identity (passes require_cloudflare_access)."""
    return {"Cf-Access-Authenticated-User-Email": email}


class TestAdminAuth:
    def test_admin_users_rejects_solo_caller(self, client):
        """No CF Access header → 401."""
        resp = client.get("/admin/users")
        assert resp.status_code == 401

    def test_admin_users_rejects_x_user_id(self, client, user_a):
        """X-User-Id is a local-dev escape hatch — it doesn't count as CF Access."""
        resp = client.get("/admin/users", headers=as_user(client, user_a))
        assert resp.status_code == 401

    def test_admin_users_accepts_cf_access_header(self, client):
        resp = client.get("/admin/users", headers=_as_cf_admin())
        assert resp.status_code == 200

    def test_whoami_echoes_identity(self, client):
        resp = client.get("/admin/whoami", headers=_as_cf_admin("grace@example.com"))
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "grace@example.com"


class TestAdminReads:
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
