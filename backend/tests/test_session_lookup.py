"""
Regression tests for lookup_session_user()'s object lifetime.

The bug: the throttled `last_seen_at` write added in v2.7 (li6) calls
session.commit() while the User loaded a few lines earlier is still in the
identity map. expire_on_commit defaults to True on our sessionmaker, so the
commit expired that User, and the subsequent session.expunge() detached an
already-expired instance. A detached, expired instance cannot reload itself,
so the caller got DetachedInstanceError on the very first attribute read —
which in practice meant `user.status` inside _resolve_session_user_id().

The failure was intermittent in a way that hid it: it only fired when the
throttle actually fired, i.e. on the first request of a brand-new session
(last_seen_at IS NULL) and then once every SESSION_LAST_SEEN_THROTTLE after.
In between, no commit ran and the same code path worked fine.

Nothing in the suite exercised lookup_session_user() directly, so 26 tests
failed downstream through the auth dependency without naming the cause.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_STATUS_ACTIVE,
    Session as SessionRow,
    User,
    get_session,
)
from backend.services.auth_security import hash_password
from backend.services.auth_sessions import (
    SESSION_LAST_SEEN_THROTTLE,
    create_session,
    lookup_session_user,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app

    with TestClient(app):
        pass


def _fresh_user(email: str) -> User:
    session = get_session()
    try:
        user = User(
            email=email.lower(),
            user_id=email.lower(),
            password_hash=hash_password("supersecret123"),
            status=USER_STATUS_ACTIVE,
            role="user",
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def _set_last_seen(token: str, value: datetime | None) -> None:
    session = get_session()
    try:
        row = session.query(SessionRow).filter(SessionRow.token == token).one()
        row.last_seen_at = value
        session.commit()
    finally:
        session.close()


class TestLookupSessionUserLifetime:

    def test_first_call_returns_a_usable_user(self):
        """
        The exact regression. A brand-new session has last_seen_at IS NULL,
        so the throttle fires on the very first lookup and the commit used to
        strand the returned User.
        """
        user = _fresh_user("detach-first@example.test")
        token = create_session(user.id, user_agent="pytest", ip="127.0.0.1")

        found = lookup_session_user(token)

        assert found is not None
        # each of these would raise DetachedInstanceError before the fix
        assert found.status == USER_STATUS_ACTIVE
        assert found.user_id == "detach-first@example.test"
        assert found.id == user.id

    def test_call_that_skips_the_throttle_also_works(self):
        """The path that always worked — guard against fixing one and breaking the other."""
        user = _fresh_user("detach-fresh@example.test")
        token = create_session(user.id, user_agent="pytest", ip="127.0.0.1")
        _set_last_seen(token, datetime.utcnow())

        found = lookup_session_user(token)

        assert found is not None
        assert found.status == USER_STATUS_ACTIVE

    def test_stale_last_seen_triggers_throttle_and_still_returns_usable_user(self):
        user = _fresh_user("detach-stale@example.test")
        token = create_session(user.id, user_agent="pytest", ip="127.0.0.1")
        stale = datetime.utcnow() - (SESSION_LAST_SEEN_THROTTLE + timedelta(minutes=5))
        _set_last_seen(token, stale)

        found = lookup_session_user(token)

        assert found is not None
        assert found.user_id == "detach-stale@example.test"

    def test_last_seen_at_is_actually_written(self):
        """
        The fix must not quietly disable the feature it's fixing. Detaching the
        user early must still leave the session row's write intact.
        """
        user = _fresh_user("detach-write@example.test")
        token = create_session(user.id, user_agent="pytest", ip="127.0.0.1")
        _set_last_seen(token, None)

        lookup_session_user(token)

        session = get_session()
        try:
            row = session.query(SessionRow).filter(SessionRow.token == token).one()
            assert row.last_seen_at is not None, "throttled last_seen_at write was lost"
        finally:
            session.close()

    def test_repeated_lookups_are_stable(self):
        """
        Before the fix this alternated: fail, pass, pass... depending on whether
        the throttle fired. Every call must now behave identically.
        """
        user = _fresh_user("detach-repeat@example.test")
        token = create_session(user.id, user_agent="pytest", ip="127.0.0.1")

        for i in range(3):
            _set_last_seen(token, None)  # force the throttle every time
            found = lookup_session_user(token)
            assert found is not None, f"lookup {i} returned None"
            assert found.status == USER_STATUS_ACTIVE, f"lookup {i} returned a stranded user"
