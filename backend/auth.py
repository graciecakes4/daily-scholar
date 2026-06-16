"""
Auth identity resolution.

Goal: turn an incoming HTTP request into a stable user_id string. Used as a
FastAPI dependency:

    from fastapi import Depends
    from .auth import get_current_user_id

    @app.get("/things")
    def list_things(user_id: str = Depends(get_current_user_id)):
        ...

Resolution order:

  1. `Cf-Access-Authenticated-User-Email` header — set by Cloudflare Access
     when the request comes through a Zero-Trust-protected origin. We trust
     this header iff the origin is configured to only accept traffic from
     Cloudflare (e.g., via firewall / IP allowlist or Cloudflare Tunnel).
  2. `X-User-Id` header — escape hatch for local development / tests when
     simulating a particular user without spinning up Cloudflare.
  3. `DEFAULT_USER_ID` (`__local__`) — the sentinel for the current solo-user
     mode. Always works; matches the schema default in migration 0003.

`require_cloudflare_access`: stricter variant that 401s if the CF header is
absent. Not used yet; wire it in once Cloudflare Access is enforcing.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from .database import DEFAULT_USER_ID


def get_current_user_id(
    cf_access_email: Optional[str] = Header(default=None, alias="Cf-Access-Authenticated-User-Email"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> str:
    """
    Resolve the current user. Returns the local sentinel when no auth headers
    are present, so existing endpoints behave identically in solo mode.
    """
    if cf_access_email:
        # email is already a stable identifier; we don't need to hash it
        return cf_access_email.strip().lower()
    if x_user_id:
        return x_user_id.strip()
    return DEFAULT_USER_ID


def require_cloudflare_access(
    cf_access_email: Optional[str] = Header(default=None, alias="Cf-Access-Authenticated-User-Email"),
) -> str:
    """
    Stricter dependency: rejects requests without a Cloudflare Access header.
    Use on endpoints that must NEVER be reachable without authenticated CF
    traffic in front (e.g., admin actions, future cross-user reads).

    Not wired up yet. Reach for this in Phase 4 when CF Access is enabled.
    """
    if not cf_access_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cloudflare Access authentication required",
        )
    return cf_access_email.strip().lower()
