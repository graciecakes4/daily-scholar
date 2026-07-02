"""
Tests for POST /topics (create_topic).

Coverage gap being closed: this endpoint previously had zero test coverage
despite carrying real branching logic (regular-user ownership stamping,
ignoring a user-supplied id, visibility defaults, admin-only id/owner
overrides). It became a load-bearing, everyday-use endpoint once the
generate-scope wizard (Settings > Scope > Generate scope) started calling
it directly instead of only the manual /topics/new form.

See test_topic_ownership.py for the broader ownership/visibility permission
matrix — this file is scoped to create_topic's own request/response
contract, not the full ownership model.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    User,
    get_session,
)
from backend.services.auth_security import hash_password


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    """Trigger the FastAPI lifespan once so Alembic + bootstrap runs."""
    from backend.main import app
    with TestClient(app):
        pass


def _seed_user(email: str, *, role: str = USER_ROLE_USER) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(),
            user_id=email.lower(),
            password_hash=hash_password("dummy12345"),
            status=USER_STATUS_ACTIVE,
            role=role,
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


def _as_email(email: str) -> dict[str, str]:
    return {"Cf-Access-Authenticated-User-Email": email}


class TestCreateTopic:

    def test_regular_user_happy_path(self, client: TestClient):
        """
        The exact path the generate-scope wizard depends on: a regular
        user POSTs name + keywords/arxiv_categories/key_concepts with no
        id/owner_user_id, and gets back an owned, private, server-id'd row.
        """
        user = _seed_user("ct-alice@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(user.user_id),
            json={
                "name": "Diffusion Models",
                "keywords": ["diffusion models", "score matching"],
                "arxiv_categories": ["cs.LG"],
                "key_concepts": ["denoising", "reverse process"],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # regular users always get a server-generated opaque id, never
        # something they could collide with another user over
        assert body["id"].startswith("usr-")
        assert body["owner_user_id"] == user.id
        assert body["visibility"] == "private"
        assert body["created_via"] == "ui"
        assert body["keywords"] == ["diffusion models", "score matching"]
        assert body["arxiv_categories"] == ["cs.LG"]
        assert body["key_concepts"] == ["denoising", "reverse process"]

    def test_regular_user_cannot_set_owner(self, client: TestClient):
        alice = _seed_user("ct-alice2@example.com")
        bob = _seed_user("ct-bob@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(alice.user_id),
            json={"name": "Spoofed", "owner_user_id": bob.id},
        )
        assert r.status_code == 403

    def test_regular_user_id_override_ignored(self, client: TestClient):
        user = _seed_user("ct-carol@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(user.user_id),
            json={"name": "Carol's Topic", "id": "not-mine-to-pick"},
        )
        assert r.status_code == 201, r.text
        # the requested id is silently ignored in favor of a server-generated one
        assert r.json()["id"] != "not-mine-to-pick"
        assert r.json()["id"].startswith("usr-")

    def test_explicit_public_visibility_honored(self, client: TestClient):
        user = _seed_user("ct-dave@example.com")
        r = client.post(
            "/topics",
            headers=_as_email(user.user_id),
            json={"name": "Shared Topic", "visibility": "public"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["visibility"] == "public"

    def test_admin_duplicate_id_conflict(self, client: TestClient):
        admin = _seed_user("ct-admin@example.com", role=USER_ROLE_ADMIN)
        first = client.post(
            "/topics",
            headers=_as_email(admin.user_id),
            json={"id": "dup-topic", "name": "First", "owner_user_id": None},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/topics",
            headers=_as_email(admin.user_id),
            json={"id": "dup-topic", "name": "Second", "owner_user_id": None},
        )
        assert second.status_code == 409
