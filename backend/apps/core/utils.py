"""Small shared helpers. Business logic belongs in each app's ``services.py``."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

DHAKA = ZoneInfo("Asia/Dhaka")


def now() -> datetime:
    """Current time, timezone-aware UTC. Wrapped so tests can freeze it in one place."""
    return timezone.now()


def to_dhaka(value: datetime) -> datetime:
    """Convert an aware datetime to Dhaka local time for display."""
    return value.astimezone(DHAKA)


def dhaka_today() -> datetime:
    """Start of the current day in Dhaka, as an aware datetime."""
    local = to_dhaka(now())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def setting(name: str, default=None):
    """Read a configurable rule.

    Indirection kept deliberately thin: when the ``PlatformSetting`` model arrives, this
    is the single place that learns to consult the database before falling back to
    settings, so callers never change.
    """
    return getattr(settings, name, default)


def plain_decimal(value) -> str:
    """Render a Decimal the way a person writes it: 2, 4.3, 100.

    `str(Decimal("2.00"))` keeps the trailing zeros and `Decimal("100.00").normalize()`
    produces `1E+2`, so neither is safe to put in front of a reader. Normalising and
    then formatting with `f` gives the plain form in every case.
    """
    from decimal import Decimal

    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value.normalize():f}"


def in_readers_language(obj, field: str = "name") -> str:
    """A catalogue label in the reader's language, falling back to English.

    Sports and product categories are generic nouns — "Football", "Drinks" — and a
    Bangla UI that labels every card in English is only half translated. They live in
    the database rather than in `messages/bn.json`, so the translation has to travel
    with the row: each gets a `<field>_bn` column, and this picks between them from the
    language Django resolved for the request (`LocaleMiddleware`, set from the
    frontend's `Accept-Language`).

    Falling back rather than raising matters: a sport an admin approved five minutes ago
    has no Bangla name yet, and showing its English one is right. Proper nouns — turf
    names, player names, product brands — are not translated at all (DECISIONS D63).
    """
    from django.utils.translation import get_language

    if (get_language() or "").startswith("bn"):
        translated = getattr(obj, f"{field}_bn", "") or ""
        if translated:
            return translated
    return getattr(obj, field)


def player_label(user) -> str:
    """What to call a player on screen, without giving away their email.

    Every roster row, board card, timeline entry and audit line needs a name for
    somebody. The obvious fallback chain ended in ``user.email``, which meant a player
    who had not finished onboarding had their email address shown to everybody who could
    see the match — a leak that nothing in the UI hinted at and no test covered
    (Phase 11 step 4).

    An email is not a display name. The chain is now: the profile name they chose, the
    name on their account, and otherwise a neutral word. Two unnamed players look alike,
    which is the correct trade: they are strangers to each other, and the app is about
    to ask them to turn up to the same pitch, not to identify each other.
    """
    profile = getattr(user, "player_profile", None)
    if profile is not None and getattr(profile, "name", ""):
        return profile.name
    return (getattr(user, "full_name", "") or "").strip() or "Player"
