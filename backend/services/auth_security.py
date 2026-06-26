"""
Password hashing + session token + user_id format validation.

Kept as a thin layer over passlib + secrets so we can swap the hashing
backend later (e.g., argon2) without rewriting callers. Every API route
and CLI script touching credentials goes through these functions.
"""

from __future__ import annotations

import re
import secrets
from typing import Optional

from passlib.context import CryptContext


# bcrypt is the default for passlib; we keep a CryptContext so future
# upgrades (argon2id, scrypt) are a deprecation list, not a rewrite.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


# Minimum length — long enough to make brute force impractical; not so long
# we annoy users. Aligns with NIST 800-63B guidance: length over complexity.
MIN_PASSWORD_LENGTH = 8


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Output is self-describing (algorithm + salt + hash)."""
    if not isinstance(plain, str) or len(plain) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against the stored hash. Constant-time."""
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        # malformed hash, unknown algorithm — treat as a non-match rather
        # than 500ing the request
        return False


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------


# 64 urlsafe chars ≈ 48 bytes of entropy — far beyond brute-force.
SESSION_TOKEN_BYTES = 48


def generate_session_token() -> str:
    """Cryptographically-strong, urlsafe session token. Goes in the cookie + DB."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


# ---------------------------------------------------------------------------
# user_id format
# ---------------------------------------------------------------------------


# Rules:
#   - 3 to 30 chars
#   - lowercase letters, digits, _ - .
#   - cannot start with `__` (reserves the `__local__` sentinel namespace)
#   - email-looking strings are allowed (the default user_id IS the email)
#
# If a user picks a plain handle, we keep it short and DNS-safe so it could
# later become a path segment ("/u/<user_id>") without escaping.
USER_ID_REGEX = re.compile(r"^[a-z0-9._-]{3,30}$")


class InvalidUserIdError(ValueError):
    """Raised by validate_user_id when the candidate fails the format rules."""


def validate_user_id(candidate: str) -> str:
    """
    Normalize + validate a candidate user_id. Returns the normalized form
    (lowercased). Raises InvalidUserIdError on failure with a human-readable
    message the API layer surfaces verbatim to the client.

    Note: uniqueness is NOT checked here — the caller does that against the
    `users` and existing user-scoped tables.
    """
    if not isinstance(candidate, str):
        raise InvalidUserIdError("user_id must be a string")
    normalized = candidate.strip().lower()
    if not normalized:
        raise InvalidUserIdError("user_id cannot be empty")
    if normalized.startswith("__"):
        # __local__ and any future double-underscore sentinels are off-limits
        raise InvalidUserIdError("user_id cannot start with '__' (reserved)")
    if not USER_ID_REGEX.match(normalized):
        # one-line explanation of what's actually allowed; emails pass this
        # because @ is NOT in the regex — but the default-from-email path
        # in the signup endpoint bypasses validate_user_id and uses the
        # email verbatim. Custom handles must be DNS-safe.
        raise InvalidUserIdError(
            "user_id must be 3-30 chars, lowercase letters/digits/_-. only"
        )
    return normalized


def default_user_id_from_email(email: str) -> str:
    """
    Derive the default user_id when the user doesn't pick a custom one:
    just the lowercased email. Bypasses the handle format rules because
    emails contain `@` which is intentionally not in USER_ID_REGEX.
    """
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------


# Conservative email regex — good enough to reject "obviously not an email"
# without trying to mirror RFC 5322. Real validation happens by sending the
# user something (Phase B's approval email, eventually verification).
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidEmailError(ValueError):
    """Raised by validate_email when the candidate isn't email-shaped."""


def validate_email(candidate: str) -> str:
    """Lowercase + smoke-test email format. Returns the normalized form."""
    if not isinstance(candidate, str):
        raise InvalidEmailError("email must be a string")
    normalized = candidate.strip().lower()
    if not _EMAIL_REGEX.match(normalized):
        raise InvalidEmailError("email is not a valid address")
    return normalized
