"""Caching helpers (Phase 11 step 3).

Two rules, and they are the whole policy:

1. **Nothing per-player is cached.** Every page behind a session is built from that
   player's own rows, and a cache keyed loosely enough to be useful would be keyed
   loosely enough to show one player another's bookings. The service worker makes the
   same call (Phase 11 step 2).
2. **What is cached is public and already stale.** The leaderboard is recomputed
   overnight and read all day; the turf list changes when an admin approves a venue.
   Serving either a minute late is not a defect — recomputing it on every request is.

Invalidation is by **version key**, not by hunting down every key that might be
affected: bumping one integer makes every key derived from it unreachable at once, and
the old entries expire on their own. That is the only invalidation story that survives
somebody adding a third filter to the turf list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.core.cache import cache

#: Short, because the cost of being a minute stale is nil and the cost of a long tail of
#: wrong data after an admin approves a turf is a support conversation.
PUBLIC_TTL = 120
#: The leaderboard is rewritten nightly, so an hour is still fresh by construction.
LEADERBOARD_TTL = 3600


def _version_key(namespace: str) -> str:
    return f"v:{namespace}"


def version(namespace: str) -> int:
    """The current generation of a namespace. Missing means 1, not an error."""
    return cache.get_or_set(_version_key(namespace), 1, None) or 1


def invalidate(namespace: str) -> None:
    """Make every cached value in a namespace unreachable, at once."""
    try:
        cache.incr(_version_key(namespace))
    except ValueError:
        # Nothing cached yet, so there is nothing to invalidate.
        cache.set(_version_key(namespace), 1, None)


def cached(namespace: str, key: str, ttl: int, build: Callable[[], Any]) -> Any:
    """Return a cached value, building it once if it is not there.

    Failures reach the caller: a cache that silently serves nothing is harder to debug
    than one that is simply absent, and `build()` is always a correct answer.
    """
    full = f"{namespace}:{version(namespace)}:{key}"
    hit = cache.get(full)
    if hit is not None:
        return hit

    value = build()
    cache.set(full, value, ttl)
    return value
