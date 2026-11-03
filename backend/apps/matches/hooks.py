"""What ``apps.matches`` attaches to the booking lifecycle.

Kept separate from ``services.py`` so the registration in ``MatchesConfig.ready()``
imports as little as possible at startup.
"""

from __future__ import annotations

from .services import create_match_for_booking, sync_match_with_booking


def on_booking_created(*, booking, squad=None, **_) -> None:
    """Every booking creates exactly one match (DOMAIN §6)."""
    create_match_for_booking(booking=booking, squad=squad)


def on_booking_transitioned(*, booking, **_) -> None:
    """Keep the match in step — a cancelled booking must not stay on the board."""
    sync_match_with_booking(booking=booking)
