"""
Self-serve forgot-password flow (li3b).

`request_reset` looks up the account by email and, if it exists and is
active, emails a single-use reset link via backend/services/email.py.
It always behaves the same way from the caller's point of view whether
or not the email matched anything — no such account, a pending/
suspended account, and a real active account all take the same code
path and produce no return value the endpoint can use to distinguish
them. That's deliberate: POST /auth/forgot-password returns one generic
"if that account exists, check your email" message no matter what, so
the endpoint can't be used to enumerate which emails have accounts.

Proving the requester controls the inbox (by having them click a link
containing a token only that email received) is the actual identity
check here — a meaningfully stronger guarantee than the email+user_id
knowledge check this replaced.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..config import get_settings
from ..database import (
    USER_STATUS_ACTIVE,
    PasswordResetToken,
    User,
    get_session,
)
from .auth_security import generate_session_token, hash_password
from .email import send_email

logger = logging.getLogger(__name__)

# Short-lived: this token stands in for "just clicked the email link",
# so it should behave like one -- long enough to not expire mid-form,
# short enough that a stale/leaked token isn't useful for long.
RESET_TOKEN_TTL_MINUTES = 30


class ResetTokenInvalid(ValueError):
    """Raised by confirm_reset: token unknown, expired, or already used."""


def request_reset(email: str) -> None:
    """
    Look up `email` (already normalized by the caller) and, if it
    belongs to an ACTIVE account, mint a single-use token and email a
    reset link. No-ops silently for unknown, pending, or suspended
    accounts — the caller's response to the requester is identical
    either way, so there's nothing useful to return here.
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.email == email).first()
        if user is None or user.status != USER_STATUS_ACTIVE:
            # Same non-outcome as "sent" from the requester's perspective —
            # no email actually goes out, and the endpoint doesn't say so.
            return

        token = generate_session_token()
        now = datetime.utcnow()
        session.add(PasswordResetToken(
            token=token,
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
        ))
        session.commit()

        reset_link = f"{get_settings().frontend_url.rstrip('/')}/reset-password?token={token}"
        send_email(
            to=user.email,
            subject="Reset your Daily Scholar password",
            text_body=(
                f"Someone (hopefully you) requested a password reset for your "
                f"Daily Scholar account.\n\n"
                f"Reset your password here (expires in {RESET_TOKEN_TTL_MINUTES} minutes):\n"
                f"{reset_link}\n\n"
                f"If you didn't request this, you can safely ignore this email — "
                f"your password won't change unless you click the link above."
            ),
            html_body=(
                f"<p>Someone (hopefully you) requested a password reset for your "
                f"Daily Scholar account.</p>"
                f'<p><a href="{reset_link}">Click here to reset your password</a> '
                f"(expires in {RESET_TOKEN_TTL_MINUTES} minutes).</p>"
                f"<p>If you didn't request this, you can safely ignore this email "
                f"— your password won't change unless you click the link above.</p>"
            ),
        )
    finally:
        session.close()


def confirm_reset(token: str, new_password: str) -> int:
    """
    Consume a reset token and set the new password. Returns the user's
    int id so the caller (the endpoint) can revoke sessions.

    Raises:
      ResetTokenInvalid -- token unknown, expired, or already used.
      ValueError        -- from hash_password if new_password is too
                            short (caller maps this to a 400 too).
    """
    session = get_session()
    try:
        row = (
            session.query(PasswordResetToken)
            .filter(PasswordResetToken.token == token)
            .first()
        )
        if row is None or row.used_at is not None or row.expires_at <= datetime.utcnow():
            raise ResetTokenInvalid("This reset link is invalid or has expired.")

        user = session.query(User).filter(User.id == row.user_id).first()
        if user is None:
            raise ResetTokenInvalid("This reset link is invalid or has expired.")

        user.password_hash = hash_password(new_password)
        row.used_at = datetime.utcnow()
        session.commit()
        return user.id
    finally:
        session.close()
