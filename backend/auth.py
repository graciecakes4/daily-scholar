"""
Auth identity resolution.

Goal: turn an incoming HTTP request into a stable user_id string. Used as a
FastAPI dependency:

    from fastapi import Depends
    from .auth import get_current_user_id

    @app.get("/things")
    def list_things(user_id: str = Depends(get_current_user_id)):
        ...

Two layers, both off by default for solo mode:

  1. Identity header (always-on when present).
     `Cf-Access-Authenticated-User-Email` — set by Cloudflare Access when the
     request comes through a Zero-Trust-protected origin. Trusted iff the
     origin is locked to CF traffic (firewall allowlist / Cloudflare Tunnel).
     Without that lockdown anyone can spoof the header — pair it with one of:
       - an L4 firewall rule that only accepts cloudflare IPs, OR
       - a Cloudflare Tunnel from cloudflared on the origin, OR
       - the JWT verification layer below (cryptographic proof, layer 2).

  2. JWT verification (optional, env-gated by CF_ACCESS_VERIFY_JWT).
     When enabled, every request must also carry `Cf-Access-Jwt-Assertion`
     signed by Cloudflare's team JWKS. The JWT is validated against the
     team's public keys (cached), the configured AUD tag, and standard
     iss/exp claims. If the JWT and email header are both present, the JWT
     `email` claim must match the header — mismatched requests are 401.
     With the flag off, the JWT (if present) is ignored.

Fallback (always available, even with JWT verification on): the local dev
escape hatch `X-User-Id` (only used when no CF headers are present), then
the `DEFAULT_USER_ID = '__local__'` sentinel for solo mode.

`require_cloudflare_access`: stricter variant that 401s if no CF identity
is established. Use on endpoints that must never be reachable from local /
unauthenticated traffic.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import Header, HTTPException, status

from .config import get_settings
from .database import DEFAULT_USER_ID


# how long (seconds) to cache the team JWKS before refetching
_JWKS_TTL_SECONDS = 3600

# in-process JWKS cache; key=team_domain, value=(fetched_at_epoch, PyJWKClient)
_jwks_cache: dict[str, tuple[float, Any]] = {}


def _get_jwks_client(team_domain: str):
    """
    Return a cached PyJWKClient pointing at this team's certs endpoint.
    PyJWKClient itself does signing-key caching keyed by `kid`, but we still
    rotate the client wholesale after _JWKS_TTL_SECONDS so a deleted key
    doesn't linger in cache indefinitely.
    """
    # local import keeps pyjwt optional when CF_ACCESS_VERIFY_JWT is off
    from jwt import PyJWKClient

    now = time.time()
    cached = _jwks_cache.get(team_domain)
    if cached and (now - cached[0]) < _JWKS_TTL_SECONDS:
        return cached[1]

    jwks_url = f"https://{team_domain}/cdn-cgi/access/certs"
    client = PyJWKClient(jwks_url)
    _jwks_cache[team_domain] = (now, client)
    return client


def _verify_cf_access_jwt(token: str) -> dict:
    """
    Verify a Cf-Access-Jwt-Assertion token against the configured team JWKS.

    Returns the decoded claims on success. Raises HTTPException(401) on any
    validation failure (missing config, bad signature, expired, wrong aud).
    The error detail is deliberately generic; specifics go to logs.
    """
    import jwt as pyjwt
    from jwt import (
        ExpiredSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidTokenError,
        PyJWKClientError,
    )

    settings = get_settings()
    team_domain = settings.cf_access_team_domain
    aud_tag = settings.cf_access_aud_tag
    if not team_domain or not aud_tag:
        # misconfiguration — fail closed
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CF_ACCESS_VERIFY_JWT is on but CF_ACCESS_TEAM_DOMAIN / CF_ACCESS_AUD_TAG are not set",
        )

    issuer = f"https://{team_domain}"

    try:
        jwks_client = _get_jwks_client(team_domain)
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        claims = pyjwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=aud_tag,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except (
        ExpiredSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidTokenError,
        PyJWKClientError,
    ) as e:
        # generic 401 — don't leak why
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cloudflare Access token",
        ) from e

    return claims


def _identity_from_jwt_claims(claims: dict) -> Optional[str]:
    """
    Pick the most stable identifier from CF Access JWT claims.
    CF puts the user email under `email`; fall back to `sub` (the CF user UUID).
    """
    email = claims.get("email")
    if isinstance(email, str) and email:
        return email.strip().lower()
    sub = claims.get("sub")
    if isinstance(sub, str) and sub:
        return sub.strip()
    return None


def _resolve_identity(
    cf_access_email: Optional[str],
    cf_access_jwt: Optional[str],
    x_user_id: Optional[str],
    *,
    require_cf: bool,
) -> str:
    """
    Shared resolution used by both get_current_user_id and require_cloudflare_access.

    - If CF_ACCESS_VERIFY_JWT is on:
        * the JWT is required (401 if missing), validated, and its identity wins.
        * if the email header is also present it must match the JWT email.
    - Otherwise:
        * the email header (if present) wins.
        * x_user_id is the local-dev escape hatch.
        * DEFAULT_USER_ID is the solo-mode fallback (unless require_cf=True,
          which 401s instead).
    """
    settings = get_settings()

    if settings.cf_access_verify_jwt:
        if not cf_access_jwt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access JWT required",
            )
        claims = _verify_cf_access_jwt(cf_access_jwt)
        jwt_identity = _identity_from_jwt_claims(claims)
        if not jwt_identity:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access token has no identifiable subject",
            )
        # if the email header tagged along, it must agree — guard against
        # a mix-and-match attack where the JWT is valid but for a different user.
        if cf_access_email and cf_access_email.strip().lower() != jwt_identity:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access header / token identity mismatch",
            )
        return jwt_identity

    # JWT verification off — header trust mode
    if cf_access_email:
        return cf_access_email.strip().lower()
    if x_user_id:
        return x_user_id.strip()
    if require_cf:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cloudflare Access authentication required",
        )
    return DEFAULT_USER_ID


def get_current_user_id(
    cf_access_email: Optional[str] = Header(default=None, alias="Cf-Access-Authenticated-User-Email"),
    cf_access_jwt: Optional[str] = Header(default=None, alias="Cf-Access-Jwt-Assertion"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> str:
    """
    Resolve the current user. Returns the local sentinel when no auth headers
    are present and CF_ACCESS_VERIFY_JWT is off, so existing endpoints behave
    identically in solo mode.
    """
    return _resolve_identity(
        cf_access_email, cf_access_jwt, x_user_id, require_cf=False,
    )


def require_cloudflare_access(
    cf_access_email: Optional[str] = Header(default=None, alias="Cf-Access-Authenticated-User-Email"),
    cf_access_jwt: Optional[str] = Header(default=None, alias="Cf-Access-Jwt-Assertion"),
) -> str:
    """
    Stricter dependency: rejects requests without a Cloudflare Access identity
    (email header or, when CF_ACCESS_VERIFY_JWT is on, a valid JWT). Use on
    endpoints that must NEVER be reachable from local / unauthenticated
    traffic — e.g., admin actions, future cross-user reads.
    """
    return _resolve_identity(
        cf_access_email, cf_access_jwt, x_user_id=None, require_cf=True,
    )
