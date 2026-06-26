"""
In-memory fixed-window rate limiter.

Implemented as a `BaseHTTPMiddleware` instead of a per-endpoint decorator
so we don't fight FastAPI's body-parameter introspection (slowapi's
decorator wraps endpoints in a way that breaks pydantic body detection).

Policies are tuples: (method, path, limit, window_seconds, key_func).
Fixed-window: each (key, path) keeps timestamps of recent requests;
expired entries are pruned at lookup time. Good enough for in-process
single-instance Daily Scholar; swap to Redis if we ever scale horizontally.

Env-flagged off via `RATE_LIMIT_DISABLED=1`. Default test conftest sets it.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from time import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _rate_limit_disabled() -> bool:
    return os.environ.get("RATE_LIMIT_DISABLED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ---------------------------------------------------------------------------
# Key functions
# ---------------------------------------------------------------------------


def ip_key(request: Request) -> str:
    """Default key: caller IP. Used by unauthenticated endpoints."""
    client = request.client
    if client is None:
        return "ip:unknown"
    return f"ip:{client.host}"


def user_or_ip_key(request: Request) -> str:
    """
    Authenticated endpoints: prefer the session-resolved user_id, fall
    back to IP. Stops one logged-in user from burning the LLM bill for
    everyone while still throttling unauthenticated callers by IP.
    """
    cookie = request.cookies.get("ds_session")
    if cookie:
        try:
            from ..services.auth_sessions import lookup_session_user

            user = lookup_session_user(cookie)
            if user is not None:
                return f"u:{user.user_id}"
        except Exception:  # noqa: BLE001 — never let key lookup break a request
            pass
    return ip_key(request)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


# Policy tuple: (method, path, max_requests, window_seconds, key_func)
Policy = tuple[str, str, int, int, Callable[[Request], str]]


DEFAULT_POLICIES: list[Policy] = [
    # POST /auth/login: 5 attempts per minute per IP — brute-force defense
    ("POST", "/auth/login", 5, 60, ip_key),
    # POST /auth/signup: 3 per minute per IP — signup flood defense
    ("POST", "/auth/signup", 3, 60, ip_key),
    # POST /onboarding/generate-topic: 5 per hour per user — LLM bill protection
    ("POST", "/onboarding/generate-topic", 5, 3600, user_or_ip_key),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-policy fixed-window in-memory rate limiter. Mount in main.py
    via `app.add_middleware(RateLimitMiddleware)`. Skipped entirely
    when RATE_LIMIT_DISABLED=1.
    """

    def __init__(self, app, policies: list[Policy] | None = None):
        super().__init__(app)
        self.policies = policies if policies is not None else DEFAULT_POLICIES
        # bucket key → list of request timestamps within the window
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if _rate_limit_disabled():
            return await call_next(request)

        method = request.method.upper()
        path = request.url.path

        for p_method, p_path, p_limit, p_window, p_key in self.policies:
            if method != p_method or path != p_path:
                continue

            bucket_key = f"{p_method} {p_path}|{p_key(request)}"
            now = time()
            # prune expired timestamps
            window_start = now - p_window
            recent = [t for t in self._buckets[bucket_key] if t >= window_start]

            if len(recent) >= p_limit:
                logger.info(
                    "rate_limit: 429 on %s %s for %s (%d in last %ds)",
                    p_method, p_path, bucket_key, len(recent), p_window,
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Too many requests; limit is {p_limit} per {p_window} seconds"},
                )

            recent.append(now)
            self._buckets[bucket_key] = recent
            break       # one policy match per request

        return await call_next(request)
