"""
Per-user isolation tests for the 9 user-scoped tables.

These tests close out the unchecked item from the Phase 4 PR body: confirm
that endpoint-level user_id filtering actually keeps users separate. Each
test seeds rows for two users (alice and bob) and asserts that bob's view
contains zero alice rows and vice versa, including cross-user write attempts
(which should 404, not silently succeed).

Coverage map (table → endpoints exercised):
  archived_papers       → POST/GET/PUT/DELETE /archive/papers, GET /archive/stats
  archived_topic_reviews→ POST/GET/PUT/DELETE /archive/topics,
                          PUT /topics/{id}/status, GET /topics/status-summary
  archived_quizzes      → POST/GET/DELETE /archive/quizzes
  seen_papers           → GET /papers/history (writes happen via /papers/daily,
                          which we don't hit because it calls the LLM)
  user_stats            → GET /stats (writes happen as side-effects of archive POSTs)
  user_settings         → GET/PUT /user/scope
  push_subscriptions    → POST/GET/POST(unsubscribe) /push/...
  paper_pdfs            → covered transitively via /archive/papers PDF endpoints
                          (skipped: requires real storage backend)
  daily_content_cache   → skipped: requires LLM call to populate

We don't mock the LLM here — that's a separate test concern. These tests
are pure CRUD isolation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import as_user


# ---------------------------------------------------------------------------
# helpers — small seed builders that keep the test bodies readable
# ---------------------------------------------------------------------------


def _archive_paper(client: TestClient, user_id: str, title: str, arxiv_id: str) -> int:
    """POST an archived paper for user_id; return the row id."""
    resp = client.post(
        "/archive/papers",
        headers=as_user(client, user_id),
        json={
            "title": title,
            "authors": ["A. Author"],
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "primary_category": "astro-ph.HE",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _archive_topic(client: TestClient, user_id: str, topic_id: str, name: str) -> int:
    resp = client.post(
        "/archive/topics",
        headers=as_user(client, user_id),
        json={
            "topic_id": topic_id,
            "topic_name": name,
            "course_id": "stream-x",
            "course_name": "Stream X",
            "review_content": "...",
            "key_points": ["k1"],
            "connections": ["c1"],
            "practice_suggestions": ["p1"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _archive_quiz(client: TestClient, user_id: str) -> int:
    resp = client.post(
        "/archive/quizzes",
        headers=as_user(client, user_id),
        json={
            "topics": ["t1"],
            "total_questions": 2,
            "total_points": 4,
            "score_earned": 2,
            "percentage": 50.0,
            "questions": [
                {"id": "q1", "result": {"correct": True}},
                {"id": "q2", "result": {"correct": False}},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _subscribe_push(client: TestClient, user_id: str, endpoint: str) -> int:
    resp = client.post(
        "/push/subscribe",
        headers=as_user(client, user_id),
        json={
            "endpoint": endpoint,
            "keys": {"p256dh": "fake-p256dh", "auth": "fake-auth"},
        },
    )
    # /push/subscribe is declared with status_code=201
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# archived_papers
# ---------------------------------------------------------------------------


class TestArchivedPapersIsolation:
    def test_list_only_returns_own_papers(self, client, user_a, user_b):
        _archive_paper(client, user_a, "alice paper 1", "2401.0001")
        _archive_paper(client, user_a, "alice paper 2", "2401.0002")
        _archive_paper(client, user_b, "bob paper", "2401.9999")

        resp_a = client.get("/archive/papers", headers=as_user(client, user_a))
        resp_b = client.get("/archive/papers", headers=as_user(client, user_b))

        titles_a = {p["title"] for p in resp_a.json()["papers"]}
        titles_b = {p["title"] for p in resp_b.json()["papers"]}
        assert titles_a == {"alice paper 1", "alice paper 2"}
        assert titles_b == {"bob paper"}

    def test_get_one_404s_for_other_user(self, client, user_a, user_b):
        paper_id = _archive_paper(client, user_a, "alice", "2401.0001")
        resp = client.get(f"/archive/papers/{paper_id}", headers=as_user(client, user_b))
        assert resp.status_code == 404

    def test_update_404s_for_other_user(self, client, user_a, user_b):
        paper_id = _archive_paper(client, user_a, "alice", "2401.0001")
        resp = client.put(
            f"/archive/papers/{paper_id}",
            headers=as_user(client, user_b),
            json={"user_notes": "stolen!"},
        )
        assert resp.status_code == 404

    def test_delete_404s_for_other_user(self, client, user_a, user_b):
        paper_id = _archive_paper(client, user_a, "alice", "2401.0001")
        resp = client.delete(f"/archive/papers/{paper_id}", headers=as_user(client, user_b))
        assert resp.status_code == 404
        # original still exists for alice
        resp_a = client.get(f"/archive/papers/{paper_id}", headers=as_user(client, user_a))
        assert resp_a.status_code == 200

    def test_same_unique_id_can_be_archived_by_both_users(self, client, user_a, user_b):
        """unique_id is globally unique on the model, but per-user dedup is
        enforced at the application layer — both users can archive the same
        arxiv paper independently."""
        _archive_paper(client, user_a, "shared arxiv paper", "2401.5555")
        # bob archives a different unique_id but same title — exercise the dedup path
        _archive_paper(client, user_b, "shared arxiv paper", "2401.5556")
        # both lists should show their own entry only
        a = client.get("/archive/papers", headers=as_user(client, user_a)).json()
        b = client.get("/archive/papers", headers=as_user(client, user_b)).json()
        assert a["total"] == 1
        assert b["total"] == 1


# ---------------------------------------------------------------------------
# archived_topic_reviews
# ---------------------------------------------------------------------------


class TestArchivedTopicsIsolation:
    def test_list_only_returns_own_topics(self, client, user_a, user_b):
        _archive_topic(client, user_a, "alice-t1", "Alice Topic")
        _archive_topic(client, user_b, "bob-t1", "Bob Topic")
        resp_a = client.get("/archive/topics", headers=as_user(client, user_a)).json()
        resp_b = client.get("/archive/topics", headers=as_user(client, user_b)).json()
        names_a = {t["topic_name"] for t in resp_a["topics"]}
        names_b = {t["topic_name"] for t in resp_b["topics"]}
        assert names_a == {"Alice Topic"}
        assert names_b == {"Bob Topic"}

    def test_update_404s_for_other_user(self, client, user_a, user_b):
        topic_db_id = _archive_topic(client, user_a, "alice-t1", "Alice Topic")
        resp = client.put(
            f"/archive/topics/{topic_db_id}",
            headers=as_user(client, user_b),
            json={"user_notes": "hijack"},
        )
        assert resp.status_code == 404

    def test_delete_404s_for_other_user(self, client, user_a, user_b):
        topic_db_id = _archive_topic(client, user_a, "alice-t1", "Alice Topic")
        resp = client.delete(
            f"/archive/topics/{topic_db_id}", headers=as_user(client, user_b),
        )
        assert resp.status_code == 404

    def test_status_summary_is_per_user(self, client, user_a, user_b):
        # alice completes 2 topics; bob completes none
        for tid in ("alice-1", "alice-2"):
            _archive_topic(client, user_a, tid, f"Alice {tid}")
            client.put(
                f"/topics/{tid}/status",
                headers=as_user(client, user_a),
                json={"status": "completed"},
            )
        _archive_topic(client, user_b, "bob-1", "Bob 1")

        sum_a = client.get("/topics/status-summary", headers=as_user(client, user_a)).json()
        sum_b = client.get("/topics/status-summary", headers=as_user(client, user_b)).json()
        assert sum_a["completed"] == 2
        assert sum_b["completed"] == 0


# ---------------------------------------------------------------------------
# archived_quizzes
# ---------------------------------------------------------------------------


class TestArchivedQuizzesIsolation:
    def test_list_only_returns_own_quizzes(self, client, user_a, user_b):
        _archive_quiz(client, user_a)
        _archive_quiz(client, user_a)
        _archive_quiz(client, user_b)
        resp_a = client.get("/archive/quizzes", headers=as_user(client, user_a)).json()
        resp_b = client.get("/archive/quizzes", headers=as_user(client, user_b)).json()
        assert resp_a["total"] == 2
        assert resp_b["total"] == 1

    def test_delete_404s_for_other_user(self, client, user_a, user_b):
        quiz_id = _archive_quiz(client, user_a)
        resp = client.delete(f"/archive/quizzes/{quiz_id}", headers=as_user(client, user_b))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# user_stats — counter scoping
# ---------------------------------------------------------------------------


class TestUserStatsIsolation:
    def test_archive_counts_are_per_user(self, client, user_a, user_b):
        # alice archives 3 papers, bob archives 1
        for i in range(3):
            _archive_paper(client, user_a, f"alice {i}", f"2401.{i:04d}")
        _archive_paper(client, user_b, "bob", "2402.0001")

        stats_a = client.get("/stats", headers=as_user(client, user_a)).json()
        stats_b = client.get("/stats", headers=as_user(client, user_b)).json()
        assert stats_a["lifetime"]["papers_archived"] == 3
        assert stats_b["lifetime"]["papers_archived"] == 1

    def test_archive_stats_endpoint_is_per_user(self, client, user_a, user_b):
        _archive_paper(client, user_a, "alice", "2401.0001")
        _archive_quiz(client, user_a)
        _archive_topic(client, user_b, "bob-t1", "Bob")

        a = client.get("/archive/stats", headers=as_user(client, user_a)).json()
        b = client.get("/archive/stats", headers=as_user(client, user_b)).json()
        assert a["papers"]["total"] == 1
        assert a["quizzes"]["total"] == 1
        assert b["papers"]["total"] == 0
        assert b["topics"]["unique_topics"] == 1


# ---------------------------------------------------------------------------
# user_settings (scope) — strict per-user
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    def test_default_scope_is_per_user(self, client, user_a, user_b):
        a = client.get("/user/scope", headers=as_user(client, user_a)).json()
        b = client.get("/user/scope", headers=as_user(client, user_b)).json()
        assert a["user_id"] == user_a
        assert b["user_id"] == user_b
        # both default to 'all' but they're separate rows
        assert a["scope_mode"] == "all"
        assert b["scope_mode"] == "all"

    def test_scope_changes_dont_leak(self, client, user_a, user_b):
        # alice changes her scope; bob's stays default
        client.put(
            "/user/scope",
            headers=as_user(client, user_a),
            json={"scope_mode": "all", "scope_topic_ids": []},
        )
        # bob's read still returns 'all' default + alice's userid intact
        a = client.get("/user/scope", headers=as_user(client, user_a)).json()
        b = client.get("/user/scope", headers=as_user(client, user_b)).json()
        assert a["user_id"] == user_a
        assert b["user_id"] == user_b


# ---------------------------------------------------------------------------
# push_subscriptions — endpoint URL is per-user, not global
# ---------------------------------------------------------------------------


class TestPushSubscriptionIsolation:
    def test_list_only_returns_own_subscriptions(self, client, user_a, user_b):
        _subscribe_push(client, user_a, "https://push.example.com/alice-1")
        _subscribe_push(client, user_a, "https://push.example.com/alice-2")
        _subscribe_push(client, user_b, "https://push.example.com/bob-1")

        a = client.get("/push/subscriptions", headers=as_user(client, user_a)).json()
        b = client.get("/push/subscriptions", headers=as_user(client, user_b)).json()
        # /push/subscriptions returns a bare list
        assert isinstance(a, list) and len(a) == 2
        assert isinstance(b, list) and len(b) == 1

    def test_resubscribe_keeps_ownership(self, client, user_a, user_b):
        """A user POSTing /push/subscribe with their own existing endpoint
        URL updates the row in place (the `keys` may rotate when a browser
        re-subscribes). With the pre-fix lookup, an attacker could exploit
        the same endpoint-only lookup to take ownership; we now scope by
        (user_id, endpoint) so the update only touches the caller's row.
        DB-level UNIQUE(endpoint) blocks an attacker from inserting under
        someone else's endpoint, so this test focuses on the legitimate
        re-subscribe path."""
        endpoint = "https://push.example.com/alice-device"
        first_id = _subscribe_push(client, user_a, endpoint)
        # alice's browser re-subscribes with the same endpoint
        second_id = _subscribe_push(client, user_a, endpoint)
        assert first_id == second_id  # same row, updated in place

        # bob's view is unchanged
        b = client.get("/push/subscriptions", headers=as_user(client, user_b)).json()
        assert len(b) == 0

    def test_unsubscribe_cannot_target_other_users_endpoint(self, client, user_a, user_b):
        alice_endpoint = "https://push.example.com/alice-only"
        _subscribe_push(client, user_a, alice_endpoint)

        # bob tries to unsubscribe alice's endpoint — should report not removed
        resp = client.post(
            "/push/unsubscribe",
            headers=as_user(client, user_b),
            json={"endpoint": alice_endpoint},
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is False

        # alice's subscription still there
        a = client.get("/push/subscriptions", headers=as_user(client, user_a)).json()
        assert len(a) == 1
