"""Server-sent events for in-app notifications (DECISIONS D54).

Redis pub/sub is the fan-out: a notification created by a web worker has to reach a
stream held open by a *different* worker, so the two cannot share memory. Redis is
already here for Celery, which is most of why SSE was the cheap answer.

Everything degrades quietly. With no Redis, `publish` does nothing and the client falls
back to the polling it already does — a missed live update is a slower bell, not a lost
notification, because the row is in the database either way.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Iterator

from django.conf import settings

logger = logging.getLogger(__name__)

#: One channel per player: a stream subscribes to its own and nothing else.
CHANNEL = "notifications:{user_id}"
#: Sent when nothing has happened, so proxies do not close an idle connection.
HEARTBEAT_SECONDS = 25


def _redis():
    """A Redis client, or None when there is not one to be had."""
    try:
        import redis
    except ImportError:  # pragma: no cover - redis ships with celery[redis]
        return None

    try:
        return redis.Redis.from_url(settings.CELERY_BROKER_URL)
    except Exception:
        logger.exception("Could not reach Redis for the notification stream")
        return None


def publish(*, notification) -> bool:
    """Send one notification to whoever is listening for that player."""
    client = _redis()
    if client is None:
        return False

    payload = json.dumps(
        {
            "id": str(notification.id),
            "kind": notification.kind,
            "title": notification.title,
            "body": notification.body,
            "url": notification.url,
            "created_at": notification.created_at.isoformat(),
        }
    )
    try:
        client.publish(CHANNEL.format(user_id=notification.user_id), payload)
    except Exception:
        logger.exception("Could not publish a notification")
        return False
    return True


def event_stream(*, user_id, keepalive: int = HEARTBEAT_SECONDS) -> Iterator[str]:
    """Yield SSE frames for one player until the client goes away.

    The first frame is sent immediately: a browser does not consider the connection open
    until something arrives, and "connected" is worth saying.
    """
    yield ": connected\n\n"

    client = _redis()
    if client is None:
        # Nothing to listen to. Closing at once is better than holding a worker open on
        # a stream that can never carry anything.
        return

    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(CHANNEL.format(user_id=user_id))
        while True:
            message = pubsub.get_message(timeout=keepalive)
            if message is None:
                yield ": keepalive\n\n"
                continue

            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode()
            yield f"event: notification\ndata: {data}\n\n"
    except GeneratorExit:
        raise
    except Exception:
        logger.exception("Notification stream failed")
    finally:
        with contextlib.suppress(Exception):
            pubsub.close()
