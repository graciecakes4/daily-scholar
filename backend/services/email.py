"""
Transactional email (li3b onward).

Thin wrapper over stdlib `smtplib` + `email.mime` — no extra dependency
needed. Configured via the SMTP_* settings in backend/config.py; every
field is optional so local dev works without real creds:

  * `smtp_host` unset  -> send_email() logs the message at INFO level
    and returns False instead of raising. This keeps
    POST /auth/forgot-password usable in a fresh local checkout with
    zero SMTP setup — the reset link just shows up in the server log
    instead of an inbox.
  * `smtp_host` set    -> connects, STARTTLS (unless smtp_use_tls is
    false), authenticates if smtp_username/smtp_password are set, and
    sends for real.

Callers should treat a False return as "not actually delivered" and
decide for themselves whether that's fatal — see
backend/services/password_reset.py for why the forgot-password flow
specifically must NOT leak delivery failures back to the requester
(that would re-open the account-enumeration hole email verification is
meant to close).
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> bool:
    """
    Send a transactional email. Returns True if it was handed off to the
    SMTP server successfully, False if SMTP isn't configured or the send
    failed. Never raises — a mail-provider hiccup must not 500 the
    request that triggered it.
    """
    settings = get_settings()

    if not settings.smtp_host:
        logger.info(
            "email (SMTP_HOST unset, not sent) to=%s subject=%r\n%s",
            to, subject, text_body,
        )
        return False

    from_email = settings.smtp_from_email or settings.smtp_username
    if not from_email:
        logger.warning(
            "email: SMTP_HOST is set but neither SMTP_FROM_EMAIL nor "
            "SMTP_USERNAME is configured — refusing to send to=%s subject=%r",
            to, subject,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{from_email}>"
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(from_email, [to], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001 — a send failure must never crash the caller
        logger.warning("email: failed to send to=%s subject=%r: %s", to, subject, e)
        return False
