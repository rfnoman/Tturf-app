"""Rate limits for the actions that reach another person (Phase 11 step 4).

The default limits in ``REST_FRAMEWORK`` are a ceiling for ordinary use. These are not:
each one covers something that lands in somebody else's inbox, queue or notifications,
and there is no legitimate reason to do any of them quickly.

They are scoped rather than global so the numbers can be read next to the thing they
protect, and each rate lives in settings (CLAUDE.md: configurable rules in one place).
"""

from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle


class ReachingPeopleThrottle(UserRateThrottle):
    """Join requests, match invites, squad invites.

    Twenty an hour is more than anybody organising a game will ever send, and far fewer
    than it takes to make the app unpleasant for somebody else.
    """

    scope = "reaching-people"


class ReportThrottle(UserRateThrottle):
    """Conduct reports, which go to a human review queue (D47).

    The queue is the scarce resource: ten an hour from one account is already more than
    a reviewer can act on, and a flood would bury the real ones.
    """

    scope = "reports"


class PlayerSearchThrottle(UserRateThrottle):
    """The player directory.

    Searchable by design (DOMAIN §3) — but searchable is not the same as scrapeable, and
    the difference is a rate. `discoverable=False` keeps somebody out of results
    entirely; this stops the rest being walked wholesale.
    """

    scope = "player-search"


class WebhookThrottle(ScopedRateThrottle):
    """Clerk's webhook, and anything else a vendor calls.

    Anonymous by nature — it authenticates by signature, not by session — so without a
    scope of its own it would share the anonymous bucket with every signed-out visitor,
    and a burst of user updates would start being dropped.
    """

    scope = "webhook"
