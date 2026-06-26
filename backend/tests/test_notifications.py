"""
Tests for the configurable notifications system.

Coverage:
  * settings shape normalization (registry-driven defaults, partial input,
    type coercion)
  * GET/PUT /notifications/settings round-trip + per-user isolation
  * GET /notifications/types stable registry list
  * builders produce well-formed payloads with the data we expect them to
    surface (study reminder pulls cached topic name; weekly recap rolls up
    streak / coverage / blind spot)
  * preview endpoint never sends; test endpoint goes through the dispatch
    path but tolerates 'no push subscribers' as success

The scheduler reload is integration-tested via the PUT response counter
rather than poking APScheduler internals (which need an event loop and are
already exercised by the FastAPI lifespan in conftest).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    ArchivedPaper,
    ArchivedTopicReview,
    DailyContentCache,
    SeenPaper,
    Topic,
    UserSettings,
    UserStats,
    get_session,
)
from backend.services import notifications as notif

from .conftest import as_user


# The clean_db fixture in conftest deletes from every table after each test,
# which fails if the schema was never created. Schema creation happens in the
# FastAPI lifespan, triggered the first time we instantiate TestClient. For
# pure-Python tests (settings shape) that don't otherwise need an HTTP layer,
# we still need the tables to exist or the autouse cleanup will explode.
@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app

    with TestClient(app):
        pass  # lifespan ran on entry, ran migrations, then exited cleanly


# ---------------------------------------------------------------------------
# settings shape
# ---------------------------------------------------------------------------


class TestEnsureSettingsShape:
    """Normalization is pure; no DB / no client needed."""

    def test_empty_input_backfills_every_type(self):
        out = notif.ensure_settings_shape(None)
        assert "timezone" in out
        assert set(out["types"].keys()) == set(notif.REGISTRY.keys())
        for entry in out["types"].values():
            assert entry["enabled"] is False
            assert isinstance(entry["cron"], str) and entry["cron"]

    def test_preserves_explicit_values(self):
        out = notif.ensure_settings_shape({
            "timezone": "Europe/London",
            "types": {"study_reminder": {"enabled": True, "cron": "30 7 * * *"}},
        })
        assert out["timezone"] == "Europe/London"
        sr = out["types"]["study_reminder"]
        assert sr["enabled"] is True
        assert sr["cron"] == "30 7 * * *"
        # other types still backfilled
        assert "paper_drop" in out["types"]
        assert out["types"]["paper_drop"]["enabled"] is False

    def test_coerces_truthy_strings_to_bool(self):
        # the UI sends real bools, but settings might get hand-edited
        out = notif.ensure_settings_shape({
            "types": {"weekly_status": {"enabled": 1, "cron": "0 0 * * 0"}},
        })
        assert out["types"]["weekly_status"]["enabled"] is True

    def test_drops_unknown_types(self):
        # if the registry shrinks (a type is removed), we just stop carrying
        # the stale key forward — the loop only iterates REGISTRY keys.
        out = notif.ensure_settings_shape({
            "types": {"removed_type": {"enabled": True, "cron": "* * * * *"}},
        })
        assert "removed_type" not in out["types"]


# ---------------------------------------------------------------------------
# /notifications/types + /notifications/settings
# ---------------------------------------------------------------------------


class TestNotificationsEndpoints:

    def test_list_types_returns_registry(self, client: TestClient, user_a):
        r = client.get("/notifications/types", headers=as_user(client, user_a))
        assert r.status_code == 200
        types = r.json()["types"]
        keys = {t["key"] for t in types}
        assert keys == set(notif.REGISTRY.keys())
        for t in types:
            assert t["label"] and t["description"] and t["default_cron"]

    def test_get_settings_returns_defaults_for_new_user(self, client: TestClient, user_a):
        r = client.get("/notifications/settings", headers=as_user(client, user_a))
        assert r.status_code == 200
        blob = r.json()
        assert "timezone" in blob
        assert set(blob["types"].keys()) == set(notif.REGISTRY.keys())
        # nothing is enabled by default — user has to opt in
        assert all(t["enabled"] is False for t in blob["types"].values())

    def test_put_settings_persists_and_reloads(self, client: TestClient, user_a):
        payload = {
            "timezone": "America/Los_Angeles",
            "types": {
                "study_reminder": {"enabled": True, "cron": "0 8 * * *"},
                "paper_drop":     {"enabled": False, "cron": "0 7 * * *"},
                "weekly_status":  {"enabled": True, "cron": "0 18 * * 0"},
                "quiz_nudge":     {"enabled": False, "cron": "0 20 * * *"},
            },
        }
        r = client.put(
            "/notifications/settings",
            headers=as_user(client, user_a),
            json=payload,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["settings"]["timezone"] == "America/Los_Angeles"
        assert body["settings"]["types"]["study_reminder"]["enabled"] is True
        assert body["settings"]["types"]["study_reminder"]["cron"] == "0 8 * * *"
        # scheduler counter present (may be 0 if scheduler disabled in tests)
        assert "scheduler" in body

        # round-trip GET sees the same blob
        r2 = client.get("/notifications/settings", headers=as_user(client, user_a))
        assert r2.json() == body["settings"]

    def test_settings_isolation_between_users(
        self, client: TestClient, user_a, user_b,
    ):
        client.put(
            "/notifications/settings",
            headers=as_user(client, user_a),
            json={
                "timezone": "America/New_York",
                "types": {"study_reminder": {"enabled": True, "cron": "15 9 * * *"}},
            },
        )
        # user_b sees defaults, not user_a's settings
        r = client.get("/notifications/settings", headers=as_user(client, user_b))
        assert r.json()["types"]["study_reminder"]["enabled"] is False
        assert r.json()["types"]["study_reminder"]["cron"] != "15 9 * * *"

    def test_preview_unknown_type_404s(self, client: TestClient, user_a):
        r = client.get("/notifications/preview/does_not_exist", headers=as_user(client, user_a))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async builder from a sync test."""
    return asyncio.get_event_loop().run_until_complete(coro) \
        if asyncio._get_running_loop() is None \
        else asyncio.run(coro)


@pytest.fixture
def alice_topic() -> Topic:
    """Insert a single topic so scope helpers have something to return."""
    session = get_session()
    try:
        t = Topic(
            id="time-domain-transients",
            name="Time-Domain Transients",
            stream="photometric_classification",
            active=True,
            weight=1.0,
            keywords=["supernova", "transient"],
            arxiv_categories=["astro-ph.HE"],
            recency_days=30,
            min_relevance=0.18,
            key_concepts=["light curve", "ZTF"],
            learning_objectives=[],
            resources=[],
            quiz_difficulty="medium",
            prerequisites=[],
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        # detach so callers can use after the session closes
        session.expunge(t)
        return t
    finally:
        session.close()


class TestStudyReminderBuilder:

    def test_falls_back_to_generic_when_no_cache(self, user_a):
        payload = asyncio.run(notif.build_study_reminder(user_a))
        assert payload is not None
        assert payload["title"] == "Time to study"
        assert "Open Daily Scholar" in payload["body"]
        assert payload["tag"] == "study-reminder"
        assert payload["url"] == "/"

    def test_uses_cached_topic_name_when_present(self, user_a, alice_topic):
        # seed a daily_content_cache row with a topic in it
        session = get_session()
        try:
            row = DailyContentCache(
                user_id=user_a,
                content_date=date.today(),
                paper_data={"title": "A Light Curve Study of SN 2025xyz"},
                topic_reviews=[{"topic": {"name": alice_topic.name}, "review": {}}],
            )
            session.add(row)
            session.commit()
        finally:
            session.close()

        payload = asyncio.run(notif.build_study_reminder(user_a))
        assert alice_topic.name in payload["body"]
        # paper title is also embedded (limited length)
        assert "Light Curve Study" in payload["body"]


class TestWeeklyStatusBuilder:

    def test_rolls_up_streak_papers_and_coverage(self, user_a, alice_topic):
        # seed: streak=5, 3 papers this week, 1 archived paper, 1 review
        session = get_session()
        try:
            session.add(UserStats(user_id=user_a, current_streak_days=5))
            now = datetime.utcnow()
            for i in range(3):
                session.add(SeenPaper(
                    user_id=user_a,
                    unique_id=f"arxiv:test{i}",
                    title=f"Paper {i}",
                    shown_date=date.today(),
                    shown_at=now,
                ))
            session.add(ArchivedPaper(
                user_id=user_a,
                unique_id="arxiv:weekly-top",
                title="Top paper this week",
                authors="[]",
                source="arxiv",
                url="https://example.com",
                user_rating=5,
                linked_topic_ids=[alice_topic.id],
                archived_at=now,
            ))
            session.add(ArchivedTopicReview(
                user_id=user_a,
                topic_id=alice_topic.id,
                topic_name=alice_topic.name,
                course_id="x", course_name="x",
                last_reviewed_at=now,
            ))
            session.commit()
        finally:
            session.close()

        payload = asyncio.run(notif.build_weekly_status(user_a))
        assert payload is not None
        body = payload["body"]
        assert "5-day streak" in body
        assert "3 papers seen" in body
        assert "1 topics touched" in body
        assert "Top paper this week" in body
        # data block preserved for the service worker
        assert payload["data"]["streak"] == 5
        assert payload["data"]["papers_seen_week"] == 3

    def test_blind_spot_surfaces_neglected_topic(self, user_a):
        """A topic with no activity this week should appear as 'focus on X'."""
        # two topics, only one has activity → the other is the blind spot
        session = get_session()
        try:
            t1 = Topic(
                id="touched", name="Touched Topic", stream="x", active=True,
                weight=1.0, keywords=[], arxiv_categories=[],
                recency_days=30, min_relevance=0.18,
                key_concepts=[], learning_objectives=[], resources=[],
                quiz_difficulty="medium", prerequisites=[],
            )
            t2 = Topic(
                id="neglected", name="Neglected Topic", stream="x", active=True,
                weight=1.0, keywords=[], arxiv_categories=[],
                recency_days=30, min_relevance=0.18,
                key_concepts=[], learning_objectives=[], resources=[],
                quiz_difficulty="medium", prerequisites=[],
            )
            session.add_all([t1, t2])
            session.add(ArchivedTopicReview(
                user_id=user_a,
                topic_id=t1.id,
                topic_name=t1.name,
                course_id="x", course_name="x",
                last_reviewed_at=datetime.utcnow(),
            ))
            session.commit()
        finally:
            session.close()

        payload = asyncio.run(notif.build_weekly_status(user_a))
        assert payload is not None
        assert payload["data"]["blind_spot"] == "Neglected Topic"
        assert "Neglected Topic" in payload["body"]


class TestQuizNudgeBuilder:

    def test_returns_none_when_no_topics_in_scope(self, user_a):
        # no topics → nothing to nudge about
        payload = asyncio.run(notif.build_quiz_nudge(user_a))
        assert payload is None

    def test_includes_due_count_and_sample(self, user_a, alice_topic):
        # one topic in scope, never reviewed → due
        payload = asyncio.run(notif.build_quiz_nudge(user_a))
        assert payload is not None
        assert payload["title"] == "Quick review?"
        assert alice_topic.name in payload["body"]
        assert payload["data"]["due_count"] == 1


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:

    def test_test_endpoint_dispatches_payload(
        self, client: TestClient, user_a, alice_topic, monkeypatch,
    ):
        """The /notifications/test/{type} endpoint should go through the
        builder → push_sender pipeline; with no subscriptions registered,
        a successful send returns counts of zero."""
        r = client.post(
            "/notifications/test/study_reminder",
            headers=as_user(client, user_a),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # either dispatched (with result counts) or skipped (no payload)
        assert "payload" in body or body.get("skipped")

    def test_test_endpoint_quiz_nudge_dispatch_path(
        self, client: TestClient, user_a,
    ):
        """
        The dispatch endpoint should always return ok=true: either
        skipped (no due topics) or sent with counters. We don't assert
        the specific branch because the conftest re-bootstraps topics
        from config/topics/*.yaml on every TestClient start, so 'no
        topics' is hard to engineer here. Builder-level skip behavior
        is exercised in TestQuizNudgeBuilder.test_returns_none_when_no_topics_in_scope.
        """
        r = client.post(
            "/notifications/test/quiz_nudge",
            headers=as_user(client, user_a),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["type"] == "quiz_nudge"

    def test_preview_endpoint_returns_payload_without_sending(
        self, client: TestClient, user_a,
    ):
        r = client.get(
            "/notifications/preview/study_reminder",
            headers=as_user(client, user_a),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "study_reminder"
        assert body["would_send"] is True
        assert "title" in body["payload"]
        assert "body" in body["payload"]
