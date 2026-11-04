"""Creating and delivering notifications (DOMAIN §11).

One entry point, :func:`notify`. Callers pass a kind and a context; this module renders
the template, stores the row, and sends the email for the kinds that warrant one.

Two rules it exists to enforce:

* **Never fail the caller.** A notification is a side effect of a booking being
  confirmed, not part of it. A broken template or a dead SMTP server must not roll back
  the transition that triggered it, so everything here is defensive and logged.
* **Send after commit.** Email goes out through ``transaction.on_commit``, so a player
  is never emailed about a booking whose transaction was rolled back.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from apps.core.utils import now

from .models import Notification, NotificationKind
from .templates import TEMPLATES

logger = logging.getLogger(__name__)


def render(kind: str, context: dict[str, Any]) -> tuple[str, str, bool]:
    """Render a template, falling back to something readable rather than raising.

    A ``KeyError`` here would mean an incomplete context taking down a booking
    transition, which is a far worse outcome than a notification reading slightly oddly.
    """
    template = TEMPLATES.get(kind)
    if template is None:
        logger.error("No notification template", extra={"kind": kind})
        return (
            NotificationKind(kind).label if kind in NotificationKind.values else kind,
            "",
            False,
        )

    def safe(text: str) -> str:
        try:
            return text.format(**context)
        except KeyError, IndexError, ValueError:
            logger.error(
                "Notification context is missing a placeholder",
                extra={"kind": kind, "keys": ",".join(sorted(context))},
            )
            return text

    return safe(template["title"]), safe(template["body"]), template["email"]


def notify(
    *,
    user,
    kind: str,
    url: str = "",
    data: dict[str, Any] | None = None,
    **context: Any,
) -> Notification | None:
    """Create one notification, and email it when the kind warrants it.

    Returns ``None`` when there is nobody to tell — a walk-in booking taken at the
    counter has no account behind it, and that is normal rather than an error.
    """
    if user is None:
        return None

    title, body, should_email = render(kind, context)
    notification = Notification.objects.create(
        user=user, kind=kind, title=title, body=body, url=url, data=data or {}
    )

    if should_email and user.email:
        # After commit: never email about a transition that then rolled back.
        transaction.on_commit(lambda: _send_email(notification))

    # Same reasoning for the two Phase 09 channels: a push to a phone and a line down an
    # open stream are both impossible to take back.
    transaction.on_commit(lambda: _deliver_live(notification))

    return notification


def _deliver_live(notification: Notification) -> None:
    """Push it to the player's phone and down any stream they have open.

    Both are best-effort by design: a notification row exists either way, and the bell
    will show it the next time the app asks.
    """
    from .push import send_push
    from .stream import publish

    try:
        send_push(notification=notification)
    except Exception:
        logger.exception("Push delivery failed", extra={"id": str(notification.id)})

    try:
        publish(notification=notification)
    except Exception:
        logger.exception("Stream delivery failed", extra={"id": str(notification.id)})


def _send_email(notification: Notification) -> None:
    try:
        send_mail(
            subject=notification.title,
            message=notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not email notification", extra={"id": str(notification.id)})
        return

    Notification.objects.filter(pk=notification.pk).update(emailed_at=now())


def notify_many(*, users, kind: str, **kwargs) -> list[Notification]:
    """Tell several people the same thing — a turf's staff, a squad's members."""
    seen: set = set()
    created = []
    for user in users:
        # The same person can be both owner and manager; tell them once.
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        notification = notify(user=user, kind=kind, **kwargs)
        if notification is not None:
            created.append(notification)
    return created


@transaction.atomic
def mark_read(*, user, ids: list | None = None) -> int:
    """Mark some or all of a user's notifications read. Returns how many changed."""
    unread = Notification.objects.filter(user=user, read_at__isnull=True)
    if ids is not None:
        unread = unread.filter(id__in=ids)
    return unread.update(read_at=now())


def unread_count(*, user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
