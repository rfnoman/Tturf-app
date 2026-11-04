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


#: How long a database override is trusted before it is read again. Short, because the
#: point of moving a rule into the database is that it takes effect without a deploy —
#: and long enough that it is not a query on every booking.
SETTING_CACHE_SECONDS = 60


def setting(name: str, default=None):
    """Read a configurable rule: the database override if there is one, else the code.

    That direction is deliberate. Every rule has a default in ``config/settings``, and a
    ``PlatformSetting`` row *overrides* it — so the app is always runnable with nothing
    in the database, and undoing a bad edit is deleting a row rather than remembering
    what the number used to be.

    The value is stored as text and parsed back to the type of the default, because the
    admin form is nicer to the people who use it than a column per type would be. An
    unparseable value falls back to the default rather than raising: a typo should
    degrade to yesterday's behaviour, not take the site down. Phase 00 promised this
    function would be the only place that learned any of it, and it is.
    """
    from django.core.cache import cache

    fallback = getattr(settings, name, default)

    cached = cache.get(f"platform-setting:{name}", "\x00")
    if cached != "\x00":
        return _coerced(cached, fallback)

    try:
        from .models import PlatformSetting

        row = PlatformSetting.objects.filter(key=name).values_list("value", flat=True).first()
    except Exception:
        # No table yet (a migration is running), no database, or it is unreachable. A
        # business rule must never be the reason a request fails.
        return fallback

    cache.set(f"platform-setting:{name}", row, SETTING_CACHE_SECONDS)
    return _coerced(row, fallback)


def _coerced(raw, fallback):
    """Read `raw` back as whatever type the code's default is."""
    if raw is None:
        return fallback

    from decimal import Decimal, InvalidOperation

    try:
        if isinstance(fallback, bool):
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(fallback, int):
            return int(str(raw).strip())
        if isinstance(fallback, Decimal):
            return Decimal(str(raw).strip())
        if isinstance(fallback, float):
            return float(str(raw).strip())
    except TypeError, ValueError, InvalidOperation:
        return fallback

    return raw


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
