"""
Tests for self-service password / username change + admin password reset.

Coverage:
  * change_password service: happy path, wrong old rejected, hashes new
  * change_username service: happy path, collision, unchanged, cascade
    across all 10 user-scoped tables (verified by seeding rows under
    the old user_id and asserting they all re-key to the new one)
  * /auth/password endpoint: 200 + revokes other sessions + preserves
    current session (cookie token), 400 on wrong old, requires auth
  * /auth/username endpoint: 200 changes, format/dup/missing-password
    error mapping, /auth/me still works post-rename
  * /admin/accounts/{id}/password endpoint: 200, revokes ALL sessions,
    audit event logged with length (NOT password), refuses self,
    refuses pending, refuses non-admin
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_SUSPENDED,
    AdminAuditEvent,
    ArchivedPaper,
    ArchivedQuiz,
    ArchivedTopicReview,
    DailyContentCache,
    PaperPDF,
    PushSubscription,
    SeenPaper,
    Session,
    Topic,
    TopicSubscription,
    User,
    UserSettings,
    UserStats,
    get_session,
)
from backend.services.account_management import (
    UsernameTaken,
    UsernameUnchanged,
    WrongPassword,
    change_password,
    change_password_admin,
    change_username,
)
from backend.services.audit_log import EventType
from backend.services.auth_security import hash_password, verify_password
from backend.services.auth_sessions import create_session


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_user(
    email: str,
    *,
    user_id: Optional[str] = None,
    password: str = "supersecret123",
    role: str = USER_ROLE_USER,
    status: str = USER_STATUS_ACTIVE,
) -> User:
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


def _as_email(email: str) -> dict[str, str]:
    return {"Cf-Access-Authenticated-User-Email": email}


# ---------------------------------------------------------------------------
# service: change_password
# ---------------------------------------------------------------------------


class TestChangePasswordService:

    def test_happy_path_replaces_hash(self):
        u = _seed_user("cp-happy@example.com")
        change_password(u.id, "supersecret123", "newsecret456")
        # verify the new password works and old one doesn't
        session = get_session()
        try:
            row = session.query(User).filter(User.id == u.id).first()
            assert verify_password("newsecret456", row.password_hash)
            assert not verify_password("supersecret123", row.password_hash)
        finally:
            session.close()

    def test_wrong_old_raises(self):
        u = _seed_user("cp-wrong@example.com")
        with pytest.raises(WrongPassword):
            change_password(u.id, "definitely-not-it", "newsecret456")

    def test_short_new_password_rejected(self):
        u = _seed_user("cp-short@example.com")
        with pytest.raises(ValueError):
            change_password(u.id, "supersecret123", "short")


# ---------------------------------------------------------------------------
# service: change_username (cascade)
# ---------------------------------------------------------------------------


class TestChangeUsernameService:

    def test_unchanged_raises(self):
        u = _seed_user("cu-same@example.com")
        with pytest.raises(UsernameUnchanged):
            change_username(u.user_id, u.user_id)

    def test_collision_raises(self):
        u = _seed_user("cu-a@example.com")
        _seed_user("cu-b@example.com")
        with pytest.raises(UsernameTaken):
            change_username(u.user_id, "cu-b@example.com")

    def test_cascade_rekeys_all_user_scoped_tables(self):
        """
        Seed one row in every user-scoped table under the old user_id;
        rename; assert every row now points at the new user_id and none
        remain under the old one.
        """
        u = _seed_user("cascade-old@example.com", user_id="cascade-old")
        old_uid = u.user_id
        new_uid = "cascade-new"

        # seed a topic owner (so subscription FK is satisfied)
        session = get_session()
        try:
            topic_owner = User(
                email="topic-owner@example.com",
                user_id="topic-owner-handle",
                password_hash=hash_password("dummy12345"),
                status=USER_STATUS_ACTIVE,
                role=USER_ROLE_USER,
                created_at=datetime.utcnow(),
                approved_at=datetime.utcnow(),
            )
            session.add(topic_owner)
            session.commit()
            session.refresh(topic_owner)
            topic_owner_id = topic_owner.id

            shared_topic = Topic(
                id="cu-shared-topic", name="t", stream="x", active=True,
                weight=1.0, keywords=[], arxiv_categories=[],
                recency_days=30, min_relevance=0.18,
                key_concepts=[], learning_objectives=[], resources=[],
                quiz_difficulty="medium", prerequisites=[],
                created_via="ui", source_yaml_present=False,
                owner_user_id=topic_owner_id, visibility="public",
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            )
            session.add(shared_topic)

            now = datetime.utcnow()
            session.add(SeenPaper(user_id=old_uid, unique_id="arxiv:cu1", title="t", shown_date=now.date(), shown_at=now))
            session.add(ArchivedPaper(user_id=old_uid, unique_id="arxiv:cu1a", title="t", authors="[]", source="x", url="x"))
            session.add(ArchivedQuiz(user_id=old_uid, topics=["x"], topic_ids=["x"], total_questions=1, total_points=1, score_earned=1, percentage=100, questions=[]))
            session.add(ArchivedTopicReview(user_id=old_uid, topic_id="x", topic_name="x", course_id="x", course_name="x"))
            session.add(PaperPDF(user_id=old_uid, original_filename="x.pdf", stored_filename="x.pdf", file_path="x.pdf"))
            session.add(DailyContentCache(user_id=old_uid, content_date=now.date()))
            session.add(UserStats(user_id=old_uid))
            session.add(UserSettings(user_id=old_uid, scope_mode="all", scope_topic_ids=[]))
            session.add(PushSubscription(user_id=old_uid, endpoint=f"https://example/push/{old_uid}", p256dh="x", auth="x"))
            session.add(TopicSubscription(user_id=old_uid, topic_id="cu-shared-topic", subscribed_at=now))
            session.commit()
        finally:
            session.close()

        counts = change_username(old_uid, new_uid)
        # every table reports at least 1 row moved
        assert counts.get("users") == 1
        for table_name in (
            "seen_papers", "archived_papers", "archived_quizzes",
            "archived_topic_reviews", "paper_pdfs", "daily_content_cache",
            "user_stats", "user_settings", "push_subscriptions",
            "topic_subscriptions",
        ):
            assert counts.get(table_name, 0) >= 1, f"no rows moved for {table_name}"

        # confirm zero remain under the old user_id (sampling a few tables)
        session = get_session()
        try:
            assert session.query(SeenPaper).filter(SeenPaper.user_id == old_uid).count() == 0
            assert session.query(TopicSubscription).filter(TopicSubscription.user_id == old_uid).count() == 0
            assert session.query(UserSettings).filter(UserSettings.user_id == old_uid).count() == 0
            # users.user_id flipped too
            row = session.query(User).filter(User.id == u.id).first()
            assert row.user_id == new_uid
        finally:
            session.close()


# ---------------------------------------------------------------------------
# /auth/password endpoint
# ---------------------------------------------------------------------------


class TestSelfPasswordEndpoint:

    def test_happy_path_revokes_other_sessions_keeps_current(self, client: TestClient):
        u = _seed_user("sp-happy@example.com")
        # log in to mint the "current" session via cookie
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})
        # seed two additional sessions to verify they get revoked
        create_session(u.id)
        create_session(u.id)

        r = client.put("/auth/password", json={
            "current_password": "supersecret123",
            "new_password": "newsecret456",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["other_sessions_revoked"] == 2

        # current session still works — /auth/me succeeds
        me = client.get("/auth/me")
        assert me.status_code == 200

        client.cookies.clear()

    def test_wrong_old_rejected(self, client: TestClient):
        u = _seed_user("sp-wrong@example.com")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})

        r = client.put("/auth/password", json={
            "current_password": "WRONG",
            "new_password": "anothernewsecret",
        })
        assert r.status_code == 400
        client.cookies.clear()

    def test_short_new_password_422(self, client: TestClient):
        u = _seed_user("sp-short@example.com")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})
        # pydantic min_length kicks in first → 422
        r = client.put("/auth/password", json={
            "current_password": "supersecret123",
            "new_password": "tiny",
        })
        assert r.status_code == 422
        client.cookies.clear()

    def test_no_cookie_401(self, client: TestClient):
        r = client.put("/auth/password", json={
            "current_password": "anything",
            "new_password": "supersecret123",
        })
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# /auth/username endpoint
# ---------------------------------------------------------------------------


class TestSelfUsernameEndpoint:

    def test_happy_path_renames_and_me_still_works(self, client: TestClient):
        u = _seed_user("su-happy@example.com", user_id="su-handle-old")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})

        r = client.put("/auth/username", json={
            "current_password": "supersecret123",
            "new_user_id": "su-handle-new",
        })
        assert r.status_code == 200, r.text
        assert r.json()["changed"] is True
        assert r.json()["new_user_id"] == "su-handle-new"

        # cookie still valid + /auth/me shows the new handle
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["profile"]["user_id"] == "su-handle-new"
        client.cookies.clear()

    def test_collision_409(self, client: TestClient):
        _seed_user("su-other@example.com", user_id="su-taken")
        u = _seed_user("su-me@example.com", user_id="su-me-handle")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})

        r = client.put("/auth/username", json={
            "current_password": "supersecret123",
            "new_user_id": "su-taken",
        })
        assert r.status_code == 409
        client.cookies.clear()

    def test_bad_format_400(self, client: TestClient):
        u = _seed_user("su-bad@example.com", user_id="su-bad-handle")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})

        r = client.put("/auth/username", json={
            "current_password": "supersecret123",
            "new_user_id": "__reserved",
        })
        assert r.status_code == 400
        client.cookies.clear()

    def test_wrong_current_password_rejected(self, client: TestClient):
        u = _seed_user("su-cwp@example.com", user_id="su-cwp-handle")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})

        r = client.put("/auth/username", json={
            "current_password": "not-correct",
            "new_user_id": "valid-new-handle",
        })
        assert r.status_code == 400
        client.cookies.clear()

    def test_identical_handle_idempotent(self, client: TestClient):
        u = _seed_user("su-same@example.com", user_id="su-same-handle")
        client.post("/auth/login", json={"email": u.email, "password": "supersecret123"})
        r = client.put("/auth/username", json={
            "current_password": "supersecret123",
            "new_user_id": "su-same-handle",
        })
        assert r.status_code == 200
        assert r.json()["changed"] is False
        client.cookies.clear()


# ---------------------------------------------------------------------------
# /admin/accounts/{id}/password endpoint
# ---------------------------------------------------------------------------


ADMIN_EMAIL = "rp-admin@example.com"


def _seed_admin(email: str = ADMIN_EMAIL) -> User:
    return _seed_user(email, role=USER_ROLE_ADMIN)


class TestAdminResetPasswordEndpoint:

    def test_happy_path_resets_and_revokes(self, client: TestClient):
        _seed_admin()
        target = _seed_user("rp-target@example.com")
        # give the target two active sessions to confirm they're nuked
        create_session(target.id)
        create_session(target.id)

        r = client.put(
            f"/admin/accounts/{target.user_id}/password",
            headers=_as_email(ADMIN_EMAIL),
            json={"new_password": "freshly-set-pw"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["sessions_revoked"] is True

        # all target sessions revoked
        session = get_session()
        try:
            active = (
                session.query(Session)
                .filter(Session.user_id == target.id, Session.revoked_at.is_(None))
                .count()
            )
            assert active == 0
            # password is updated — old fails, new works
            row = session.query(User).filter(User.id == target.id).first()
            assert verify_password("freshly-set-pw", row.password_hash)
            assert not verify_password("supersecret123", row.password_hash)
        finally:
            session.close()

    def test_audit_event_logged_with_length_not_password(self, client: TestClient):
        _seed_admin()
        target = _seed_user("rp-audit@example.com")
        client.put(
            f"/admin/accounts/{target.user_id}/password",
            headers=_as_email(ADMIN_EMAIL),
            json={"new_password": "exactly-twelve"},
        )
        session = get_session()
        try:
            ev = (
                session.query(AdminAuditEvent)
                .filter(
                    AdminAuditEvent.event_type == EventType.USER_PASSWORD_RESET_ADMIN,
                    AdminAuditEvent.target_id == target.user_id,
                )
                .order_by(AdminAuditEvent.created_at.desc())
                .first()
            )
            assert ev is not None
            md = ev.audit_metadata or {}
            assert md.get("new_password_length") == len("exactly-twelve")
            # password text never leaked
            assert "exactly-twelve" not in str(md)
        finally:
            session.close()

    def test_self_reset_refused(self, client: TestClient):
        admin = _seed_admin()
        # second admin to dodge last-admin protection in unrelated tests
        _seed_admin("rp-second-admin@example.com")
        r = client.put(
            f"/admin/accounts/{admin.user_id}/password",
            headers=_as_email(ADMIN_EMAIL),
            json={"new_password": "irrelevant-but-long"},
        )
        assert r.status_code == 400
        assert "self-service" in r.json()["detail"].lower()

    def test_pending_target_refused(self, client: TestClient):
        _seed_admin()
        target = _seed_user("rp-pending@example.com", status=USER_STATUS_PENDING)
        r = client.put(
            f"/admin/accounts/{target.user_id}/password",
            headers=_as_email(ADMIN_EMAIL),
            json={"new_password": "anything-long-enough"},
        )
        assert r.status_code == 400
        assert "pending" in r.json()["detail"].lower()

    def test_non_admin_403(self, client: TestClient):
        regular = _seed_user("rp-reg@example.com")
        target = _seed_user("rp-target2@example.com")
        r = client.put(
            f"/admin/accounts/{target.user_id}/password",
            headers=_as_email(regular.user_id),
            json={"new_password": "doesnt-matter-here"},
        )
        assert r.status_code == 403

    def test_short_password_422(self, client: TestClient):
        _seed_admin()
        target = _seed_user("rp-shortpw@example.com")
        r = client.put(
            f"/admin/accounts/{target.user_id}/password",
            headers=_as_email(ADMIN_EMAIL),
            json={"new_password": "tiny"},
        )
        # pydantic min_length blocks before the handler runs
        assert r.status_code == 422
