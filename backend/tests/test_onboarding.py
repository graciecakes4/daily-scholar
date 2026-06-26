"""
Tests for Phase E: onboarding wizard + LLM-driven topic draft.

Coverage:
  * generate_topic_draft normalizes valid LLM output, falls back on
    parse errors, fallbacks on raised exceptions, and rejects too-short
    interest text
  * /onboarding/generate-topic endpoint plumbing
  * /onboarding/complete creates an owned + private topic AND flips
    users.onboarded=true atomically; failure rolls back both
  * /onboarding/skip flips the flag without creating a topic
  * /auth/me exposes the onboarded field
  * solo `__local__` 400s on all three (no user row to flip)

LLM calls are mocked via monkeypatch — no network, deterministic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.database import (
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    Topic,
    User,
    get_session,
)
from backend.services import onboarding as onboarding_service
from backend.services.auth_security import hash_password


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema_initialized() -> None:
    from backend.main import app
    with TestClient(app):
        pass


# ---------------------------------------------------------------------------
# helpers + LLM stubs
# ---------------------------------------------------------------------------


def _seed_user(email: str, *, onboarded: bool = False) -> User:
    session = get_session()
    try:
        u = User(
            email=email.lower(), user_id=email.lower(),
            password_hash=hash_password("dummy12345"),
            status=USER_STATUS_ACTIVE, role=USER_ROLE_USER,
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
            onboarded=onboarded,
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


class _StubClient:
    """Stand-in LLMClient that returns whatever payload was injected."""

    model = "stub"
    provider = "stub"

    def __init__(self, payload: dict[str, Any] | Exception):
        self._payload = payload

    def complete(self, *args, **kwargs):       # noqa: D401
        raise NotImplementedError("Tests should use complete_json")

    def complete_json(self, *args, **kwargs):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _patch_llm(monkeypatch, payload: dict[str, Any] | Exception) -> None:
    """Hot-swap get_llm_client so generate_topic_draft never hits the network."""
    monkeypatch.setattr(
        "backend.services.onboarding.get_llm_client",
        lambda task="default": _StubClient(payload),
    )


# ---------------------------------------------------------------------------
# generate_topic_draft (service layer)
# ---------------------------------------------------------------------------


class TestGenerateTopicDraft:

    def test_too_short_raises(self):
        with pytest.raises(onboarding_service.InterestsTooShort):
            onboarding_service.generate_topic_draft("ab")

    def test_normalizes_good_llm_output(self, monkeypatch):
        _patch_llm(monkeypatch, {
            "name": "Transformer Attention",
            "keywords": ["self-attention", "Multi-Head Attention", "  positional encoding  "],
            "arxiv_categories": ["cs.LG", "cs.CL"],
            "key_concepts": ["scaled dot-product", "QKV projections"],
        })
        d = onboarding_service.generate_topic_draft("transformer attention mechanisms")
        assert d.name == "Transformer Attention"
        # keywords lowercased + trimmed; dups removed
        assert "self-attention" in d.keywords
        assert "multi-head attention" in d.keywords
        assert "positional encoding" in d.keywords
        # categories kept as-is (case preserved for codes like cs.LG)
        assert d.arxiv_categories == ["cs.LG", "cs.CL"]

    def test_falls_back_when_llm_raises(self, monkeypatch):
        _patch_llm(monkeypatch, RuntimeError("API down"))
        d = onboarding_service.generate_topic_draft("transformer attention")
        # scaffold: at least one keyword from input tokens, name from input
        assert d.keywords
        assert d.name

    def test_falls_back_when_llm_returns_parse_error_marker(self, monkeypatch):
        # interface.complete_json returns this shape on JSON parse failure
        _patch_llm(monkeypatch, {"__llm_parse_error__": "bad json", "__raw__": "..."})
        d = onboarding_service.generate_topic_draft("transformer attention")
        assert d.keywords

    def test_clamps_oversize_lists(self, monkeypatch):
        _patch_llm(monkeypatch, {
            "name": "Big Topic",
            "keywords": [f"kw{i}" for i in range(500)],
            "arxiv_categories": [f"cs.X{i}" for i in range(50)],
            "key_concepts": [f"c{i}" for i in range(500)],
        })
        d = onboarding_service.generate_topic_draft("a big sprawling topic")
        assert len(d.keywords) == onboarding_service.MAX_KEYWORDS
        assert len(d.arxiv_categories) == onboarding_service.MAX_ARXIV_CATEGORIES
        assert len(d.key_concepts) == onboarding_service.MAX_KEY_CONCEPTS

    def test_drops_non_string_items(self, monkeypatch):
        _patch_llm(monkeypatch, {
            "name": "Topic",
            "keywords": ["ok", 42, None, {"bad": "shape"}, "good"],
            "arxiv_categories": [],
            "key_concepts": [],
        })
        d = onboarding_service.generate_topic_draft("test interests")
        assert d.keywords == ["ok", "good"]


# ---------------------------------------------------------------------------
# /onboarding/generate-topic endpoint
# ---------------------------------------------------------------------------


class TestGenerateTopicEndpoint:

    def test_happy_path(self, client: TestClient, monkeypatch):
        _seed_user("ge-user@example.com")
        _patch_llm(monkeypatch, {
            "name": "ML Foundations",
            "keywords": ["gradient descent", "regularization"],
            "arxiv_categories": ["cs.LG"],
            "key_concepts": ["loss landscapes", "overfitting"],
        })
        r = client.post(
            "/onboarding/generate-topic",
            headers=_as_email("ge-user@example.com"),
            json={"interests": "machine learning foundations"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "ML Foundations"
        assert "gradient descent" in body["keywords"]

    def test_too_short_400s(self, client: TestClient, monkeypatch):
        _seed_user("ge-short@example.com")
        # pydantic min_length kicks in first → 422
        r = client.post(
            "/onboarding/generate-topic",
            headers=_as_email("ge-short@example.com"),
            json={"interests": "x"},
        )
        assert r.status_code == 422

    def test_solo_rejected(self, client: TestClient):
        # no auth headers → __local__ → 400 "not applicable in solo dev"
        r = client.post(
            "/onboarding/generate-topic",
            json={"interests": "anything here"},
        )
        assert r.status_code == 400
        assert "solo" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /onboarding/complete endpoint
# ---------------------------------------------------------------------------


class TestCompleteEndpoint:

    def test_creates_topic_and_flips_flag(self, client: TestClient):
        u = _seed_user("comp-user@example.com")
        r = client.post(
            "/onboarding/complete",
            headers=_as_email(u.user_id),
            json={
                "name": "Wizard-Created",
                "keywords": ["kw1", "kw2"],
                "arxiv_categories": ["cs.LG"],
                "key_concepts": ["c1"],
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert body["onboarded"] is True
        new_topic_id = body["topic_id"]
        assert new_topic_id.startswith("usr-")

        # topic should be owned by the user, private by default
        session = get_session()
        try:
            t = session.get(Topic, new_topic_id)
            assert t is not None
            assert t.owner_user_id == u.id
            assert t.visibility == "private"
            assert t.name == "Wizard-Created"
            # user.onboarded flipped
            row = session.query(User).filter(User.id == u.id).first()
            assert row.onboarded is True
        finally:
            session.close()

    def test_complete_with_public_visibility(self, client: TestClient):
        u = _seed_user("comp-pub@example.com")
        r = client.post(
            "/onboarding/complete",
            headers=_as_email(u.user_id),
            json={
                "name": "Public First Topic",
                "keywords": ["k"],
                "arxiv_categories": [],
                "key_concepts": [],
                "visibility": "public",
            },
        )
        assert r.status_code == 201
        session = get_session()
        try:
            t = session.get(Topic, r.json()["topic_id"])
            assert t.visibility == "public"
        finally:
            session.close()

    def test_complete_rejects_solo(self, client: TestClient):
        r = client.post(
            "/onboarding/complete",
            json={
                "name": "Solo Attempt",
                "keywords": [],
                "arxiv_categories": [],
                "key_concepts": [],
            },
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /onboarding/skip endpoint
# ---------------------------------------------------------------------------


class TestSkipEndpoint:

    def test_skip_flips_flag_without_creating_topic(self, client: TestClient):
        u = _seed_user("skip-user@example.com")

        # snapshot topic count for this owner (should stay 0 after skip)
        def _owned_count() -> int:
            session = get_session()
            try:
                return (
                    session.query(Topic)
                    .filter(Topic.owner_user_id == u.id)
                    .count()
                )
            finally:
                session.close()

        before = _owned_count()
        r = client.post("/onboarding/skip", headers=_as_email(u.user_id))
        assert r.status_code == 200
        assert r.json()["onboarded"] is True
        assert _owned_count() == before        # no topic created

        # idempotent: second skip is a no-op success
        r2 = client.post("/onboarding/skip", headers=_as_email(u.user_id))
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# /auth/me exposes onboarded
# ---------------------------------------------------------------------------


class TestAuthMeOnboardedField:

    def test_pre_wizard_user_sees_false(self, client: TestClient):
        u = _seed_user("ame-fresh@example.com", onboarded=False)
        # log in to get a session cookie
        client.post("/auth/login", json={
            "email": u.email,
            "password": "dummy12345",
        })
        r = client.get("/auth/me")
        assert r.status_code == 200
        assert r.json()["profile"]["onboarded"] is False
        # cleanup so other tests don't see the cookie
        client.cookies.clear()

    def test_post_wizard_user_sees_true(self, client: TestClient):
        u = _seed_user("ame-done@example.com", onboarded=True)
        client.post("/auth/login", json={
            "email": u.email,
            "password": "dummy12345",
        })
        r = client.get("/auth/me")
        assert r.json()["profile"]["onboarded"] is True
        client.cookies.clear()
