"""
Double-submit-cookie CSRF protection.

How it works:
  1. The middleware sets a non-HttpOnly cookie `ds_csrf` containing a
     cryptographically random token whenever the incoming request lacks
     one. Non-HttpOnly because the frontend's JS needs to read it.
  2. On every non-GET/HEAD/OPTIONS request, the middleware requires an
     `X-CSRF-Token` header that matches the cookie value. Mismatch or
     missing → 403.

Why this works: a cross-origin attacker can make a forged request that
includes our cookies (SameSite=Lax permitting), but their JS can't read
the `ds_csrf` cookie value from our origin, so they can't construct the
matching header. Our same-origin frontend reads its own cookies fine.

Env-flagged off via `CSRF_DISABLED=1`. The default test conftest sets
it; production stays on.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# Cookie + header names — keep these in lockstep with frontend/lib/api.ts
CSRF_COOKIE_NAME = "ds_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_TOKEN_BYTES = 32         # 32 bytes → 43-char urlsafe; far beyond brute-force


# Methods that mutate state need a CSRF check. GET/HEAD/OPTIONS are safe.
PROTECTED_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))


def _csrf_disabled() -> bool:
    return os.environ.get("CSRF_DISABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _new_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def _cookie_secure() -> bool:
    """Mirror the session cookie's Secure flag policy."""
    val = os.environ.get("SESSION_COOKIE_SECURE")
    if val is None:
        # if debug is set, this is local dev → no Secure flag
        from ..config import get_settings
        return not get_settings().debug
    return val.strip().lower() in ("1", "true", "yes", "on")


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Validates the double-submit cookie on every mutating request, and
    sets the cookie on every response that doesn't already have one.

    Mounted from `main.py`. Skipped entirely when CSRF_DISABLED=1.
    """

    async def dispatch(self, request: Request, call_next):
        if _csrf_disabled():
            return await call_next(request)

        method = request.method.upper()
        cookie_token: Optional[str] = request.cookies.get(CSRF_COOKIE_NAME)

        if method in PROTECTED_METHODS:
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if not cookie_token or not header_token or cookie_token != header_token:
                # 403 with a clear-enough detail that the frontend can
                # retry after refreshing the cookie. Don't leak which
                # half was the miss.
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"},
                )

        # let the request through
        response = await call_next(request)

        # ensure the caller has a fresh cookie for the next request.
        # If they came in with one, leave it alone — rotating per request
        # would race with multi-tab sessions.
        if not cookie_token:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=_new_token(),
                # NOT HttpOnly — the frontend's JS needs to read it
                httponly=False,
                secure=_cookie_secure(),
                samesite="lax",
                path="/",
                max_age=30 * 24 * 3600,    # 30 days, matches session cookie
            )
        return response
