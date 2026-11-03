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
