"""Web push delivery (DECISIONS D55).

Encrypting a Web Push payload is ECDH + HKDF + AES-GCM under a VAPID-signed JWT, so the
encryption is `pywebpush`'s job and the policy is ours: who asked for push, which kinds
they want, and what to do when a subscription turns out to be dead.

With no VAPID keys configured — development, CI — every send is skipped and said so in
the log. Nothing here ever raises into a caller: a notification that failed to reach a
phone must not undo the thing that caused it.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.VAPID_PRIVATE_KEY)


def send_push(*, notification) -> int:
    """Push one notification to every browser this player has registered.

    Returns how many browsers took it. A subscription the push service reports as gone
    (404/410) is deleted — that is the only way a browser tells us it has forgotten.
    """
    from apps.fitness.models import PushSubscription
    from apps.fitness.services import reminder_preference

    if not is_configured():
        logger.debug("Web push is not configured; skipping")
        return 0

    preference = reminder_preference(notification.user)
    if not preference.push_enabled:
        return 0

    payload = json.dumps(
        {
            "title": notification.title,
            "body": notification.body,
            "url": notification.url or "/",
            "kind": notification.kind,
        }
    )

    sent = 0
    for subscription in PushSubscription.objects.filter(player=notification.user):
        if _deliver(subscription=subscription, payload=payload):
            sent += 1

    return sent


def _deliver(*, subscription, payload: str) -> bool:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}"},
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            # The browser has forgotten us. Deleting is the whole clean-up story.
            subscription.delete()
            logger.info("Dropped a dead push subscription", extra={"status": status})
        else:
            logger.warning("Web push failed", extra={"status": status})
        return False
    except Exception:
        logger.exception("Web push blew up")
        return False

    from apps.core.utils import now

    subscription.last_used_at = now()
    subscription.save(update_fields=["last_used_at", "updated_at"])
    return True
