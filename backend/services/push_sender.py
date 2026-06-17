"""
Web Push fanout.

`send_push_to_user(user_id, payload)` posts a JSON payload to every active
PushSubscription for that user. Dead subscriptions (HTTP 410 Gone from the
push provider) are pruned automatically; transient failures (network errors,
5xx) are logged and skipped without removing the row.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from pywebpush import WebPushException, webpush

from ..config import get_settings
from ..database import PushSubscription, get_session

logger = logging.getLogger(__name__)


def send_push_to_user(user_id: str, payload: dict[str, Any]) -> dict[str, int]:
    """
    Fan out a push payload to every subscription belonging to `user_id`.

    `payload` is JSON-encoded and delivered as the body of the push event;
    the service worker reads it in its 'push' handler. Suggested shape:
        {"title": "...", "body": "...", "url": "/papers/123", "tag": "daily-paper"}

    Returns a counter dict: {"sent": N, "removed": M, "failed": K}.
    """
    settings = get_settings()
    if not (settings.vapid_public_key and settings.vapid_private_key and settings.vapid_subject):
        logger.warning("send_push_to_user: VAPID not configured, skipping fanout")
        return {"sent": 0, "removed": 0, "failed": 0, "skipped": "vapid_not_configured"}

    vapid_claims = {"sub": settings.vapid_subject}
    body = json.dumps(payload)

    sent = removed = failed = 0
    session = get_session()
    try:
        subs = (
            session.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .all()
        )
        if not subs:
            logger.info("send_push_to_user: no subscriptions for %s", user_id)
            return {"sent": 0, "removed": 0, "failed": 0, "subscriptions": 0}

        dead_ids: list[int] = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=body,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims=dict(vapid_claims),  # webpush mutates this; pass a fresh copy
                )
                sub.last_used_at = datetime.utcnow()
                sent += 1
            except WebPushException as e:
                # 404 / 410 mean the browser killed this subscription — drop the row
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):
                    dead_ids.append(sub.id)
                    removed += 1
                    logger.info("push: dropped dead subscription %s (status %s)", sub.id, status)
                else:
                    failed += 1
                    logger.warning("push: send failed for sub %s: %s", sub.id, e)
            except Exception as e:  # noqa: BLE001 — keep going even on weird errors
                failed += 1
                logger.warning("push: unexpected error for sub %s: %s", sub.id, e)

        if dead_ids:
            session.query(PushSubscription).filter(PushSubscription.id.in_(dead_ids)).delete(
                synchronize_session=False
            )
        session.commit()
    finally:
        session.close()

    return {"sent": sent, "removed": removed, "failed": failed}
