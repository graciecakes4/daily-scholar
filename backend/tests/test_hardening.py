"""
Tests for beta hardening: rate limiting + CSRF middleware.

These features are env-flagged OFF in the global conftest so the rest
of the suite doesn't have to dance around them. This file flips them
ON via monkeypatch + a custom TestClient so we can exercise the real
behavior.

Important caveat: the rate-limiter and CSRF middleware are constructed
at FastAPI app-import time. We can't just monkeypatch env vars and
expect the existing `client` fixture to see the change — the limiter's
`enabled` flag and the CSRF middleware's class are already wired into
the app instance. So for these tests we:

  1. Set the env var BEFORE the fresh `from backend.main import app`
     (force a reimport via importlib).
  2. Construct our own TestClient against that fresh app.
  3. Clean up by clearing the env var + restoring modules in the
     fixture teardown.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hardened_client(monkeypatch) -> Iterator[TestClient]:
    """
    A fresh TestClient with RATE_LIMIT and CSRF both enabled. Reimports
    backend.main + backend.services.rate_limit + backend.middleware.csrf
    so the new env values take effect.
    """
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "0")
    monkeypatch.setenv("CSRF_DISABLED", "0")

    # Drop the cached modules so the next import re-reads the env.
    for mod_name in list(sys.modules):
        if (
            mod_name == "backend.main"
            or mod_name.startswith("backend.middleware")
            or mod_name == "backend.services.rate_limit"
            or mod_name.startswith("backend.api")     # endpoints rebind decorators
        ):
            sys.modules.pop(mod_name, None)

    from backend.main import app as fresh_app  # noqa: E402

    with TestClient(fresh_app) as c:
        yield c

    # restore: drop the hardened modules so subsequent tests get the
    # default (disabled) versions back
    for mod_name in list(sys.modules):
        if (
            mod_name == "backend.main"
            or mod_name.startswith("backend.middleware")
            or mod_name == "backend.services.rate_limit"
            or mod_name.startswith("backend.api")
        ):
            sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimitLogin:

    def test_login_429_after_burst(self, hardened_client: TestClient):
        # rule: 5/minute. Sixth attempt should 429.
        last = None
        for _ in range(6):
            last = hardened_client.post("/auth/login", json={
                "email": "nobody@example.com",
                "password": "doesnt-matter",
            })
        # the sixth call should be rate-limited
        assert last is not None and last.status_code == 429


class TestRateLimitSignup:

    def test_signup_429_after_burst(self, hardened_client: TestClient):
        # rule: 3/minute. Fourth attempt should 429.
        # We use OPEN_SIGNUP=1 from conftest so we don't need invite codes.
        last = None
        for i in range(4):
            last = hardened_client.post("/auth/signup", json={
                "email": f"rl-signup-{i}@example.com",
                "password": "supersecret123",
            })
        assert last is not None and last.status_code == 429


class TestRateLimitDisabledFlag:

    def test_default_conftest_disables_limiting(self, client: TestClient):
        # the standard `client` fixture has RATE_LIMIT_DISABLED=1 by
        # conftest. We should be able to hit login many times without 429.
        for _ in range(10):
            r = client.post("/auth/login", json={
                "email": "nobody@example.com",
                "password": "doesnt-matter",
            })
            assert r.status_code != 429


# ---------------------------------------------------------------------------
# CSRF middleware
# ---------------------------------------------------------------------------


class TestCSRF:

    def test_get_skipped(self, hardened_client: TestClient):
        # GET requests don't need CSRF; this should NOT 403
        r = hardened_client.get("/auth/me")
        # 401 is fine (no session); 403 would mean CSRF kicked in incorrectly
        assert r.status_code != 403

    def test_cookie_set_on_first_response(self, hardened_client: TestClient):
        # first request — no cookie sent in — server should set ds_csrf
        hardened_client.get("/auth/me")
        assert "ds_csrf" in hardened_client.cookies

    def test_post_without_token_403s(self, hardened_client: TestClient):
        # send POST without first having a cookie OR a header → 403
        r = hardened_client.post("/auth/login", json={
            "email": "x@example.com",
            "password": "doesnt-matter",
        })
        # could be 401 (login) or 429 (rate limit, but we haven't burst yet)
        # but the CSRF middleware sits in front of the route — should 403
        assert r.status_code == 403
        assert "csrf" in r.json()["detail"].lower()

    def test_post_with_matching_token_passes_csrf(self, hardened_client: TestClient):
        # first warm up the cookie via a GET
        hardened_client.get("/auth/me")
        token = hardened_client.cookies.get("ds_csrf")
        assert token is not None

        # now POST with matching header
        r = hardened_client.post(
            "/auth/login",
            headers={"X-CSRF-Token": token},
            json={"email": "x@example.com", "password": "doesnt-matter"},
        )
        # CSRF passes; login itself fails with 401 (unknown email)
        assert r.status_code == 401

    def test_post_with_mismatched_token_403s(self, hardened_client: TestClient):
        hardened_client.get("/auth/me")
        r = hardened_client.post(
            "/auth/login",
            headers={"X-CSRF-Token": "completely-wrong-value"},
            json={"email": "x@example.com", "password": "doesnt-matter"},
        )
        assert r.status_code == 403


class TestCSRFDisabledFlag:

    def test_default_conftest_disables_csrf(self, client: TestClient):
        # standard `client` has CSRF_DISABLED=1, so POSTs without any
        # X-CSRF-Token header should NOT 403
        r = client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "doesnt-matter",
        })
        assert r.status_code != 403   # 401 expected (bad creds)
