"""
Backwards-compat shim — the rate limiter now lives in
backend/middleware/rate_limit.py as a true middleware (no per-endpoint
decorator) because slowapi's decorator was breaking FastAPI's
body-parameter introspection.

Re-exports the env-flag helper for callers that imported it from here.
"""

from __future__ import annotations

from ..middleware.rate_limit import _rate_limit_disabled  # noqa: F401

__all__ = ["_rate_limit_disabled"]
