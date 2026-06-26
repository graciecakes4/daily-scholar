"""
Pytest fixtures for backend tests.

Key design choice: every test session gets its own SQLite file under tmp/, and
we bypass Alembic by calling `Base.metadata.create_all` directly. Alembic is
exercised in CI against both SQLite and Postgres via a separate job; the
isolation tests only care that endpoint queries return the right per-user rows.

Two-user pattern: tests get a TestClient plus helpers that stamp each request
with `X-User-Id: <id>`. CF_ACCESS_VERIFY_JWT is off in tests, so the email
header path resolves identity exactly like the local-dev escape hatch.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

# IMPORTANT: set DATABASE_URL *before* importing anything from backend so the
# settings cache picks it up on first read.
_TEST_DB = Path("/tmp/daily_scholar_pytest.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
# the app requires an Anthropic key to import; tests don't hit the LLM so a
# dummy value is fine.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-not-used")
# explicitly *off* — these tests exercise solo + X-User-Id behavior, not JWT.
os.environ["CF_ACCESS_VERIFY_JWT"] = "0"
# tests bypass the Phase B signup gate by default so the signup-mechanics
# suite doesn't need an invite code in every call. The Phase B gate-tests
# in test_invites.py override OPEN_SIGNUP per-test via monkeypatch.
os.environ.setdefault("OPEN_SIGNUP", "1")

from fastapi.testclient import TestClient  # noqa: E402

from backend import database as db_module  # noqa: E402
from backend.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _reset_test_db() -> Iterator[None]:
    """
    Drop the test DB once per session. The FastAPI app's lifespan hook
    (triggered the first time we instantiate `TestClient`) runs Alembic
    migrations end-to-end against the empty file, which is what we want —
    tests exercise the real production schema, not a `metadata.create_all`
    approximation.
    """
    if _TEST_DB.exists():
        _TEST_DB.unlink()
    yield
    # leave the file behind for postmortem; /tmp gets reaped anyway


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    """
    Wipe every table between tests so cross-test pollution can't mask bugs.
    Cheaper than dropping+recreating the schema.
    """
    yield
    engine = db_module.get_engine()
    with engine.begin() as conn:
        # reverse order so child rows (FKs) go before parents
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client() -> Iterator[TestClient]:
    """
    Bare TestClient. Use `as_user(client, '...')` to set the identity header.
    """
    # local import so the env vars above are guaranteed to be applied first
    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def user_a() -> str:
    return "alice@example.com"


@pytest.fixture
def user_b() -> str:
    return "bob@example.com"


def as_user(client: TestClient, user_id: str) -> dict[str, str]:
    """
    Return the headers dict that stamps a request as `user_id`. Pass through to
    requests:  client.get(url, headers=as_user(client, user_id)).

    Uses X-User-Id (the local-dev escape hatch) instead of the CF header so
    tests don't accidentally exercise the JWT verification path.
    """
    return {"X-User-Id": user_id}
