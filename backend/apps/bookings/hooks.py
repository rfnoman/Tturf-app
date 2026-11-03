"""Hooks other apps attach to the booking lifecycle.

Phase 04 needs a ``Match`` for every booking (DOMAIN §6), but ``Match`` holds the FK, so
``apps.bookings`` must not import ``apps.matches``. The same registry pattern Phase 02
used for availability (DECISIONS D25) keeps the dependency pointing one way.

Hooks run **inside** the creating transaction, so a hook that raises rolls the booking
back — which is what we want: a booking with no match is not a thing the rest of the app
knows how to handle.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

BookingCreatedHook = Callable[..., None]

_booking_created_hooks: list[BookingCreatedHook] = []


def register_booking_created_hook(hook: BookingCreatedHook) -> None:
    """Called from an ``AppConfig.ready()``, which can run twice under the autoreloader."""
    if hook not in _booking_created_hooks:
        _booking_created_hooks.append(hook)


def clear_booking_created_hooks() -> None:
    """Test hook."""
    _booking_created_hooks.clear()


def booking_created(*, booking, **context) -> None:
    for hook in _booking_created_hooks:
        hook(booking=booking, **context)


BookingTransitionHook = Callable[..., None]

_booking_transition_hooks: list[BookingTransitionHook] = []


def register_booking_transition_hook(hook: BookingTransitionHook) -> None:
    if hook not in _booking_transition_hooks:
        _booking_transition_hooks.append(hook)


def clear_booking_transition_hooks() -> None:
    """Test hook."""
    _booking_transition_hooks.clear()


def booking_transitioned(*, booking, **context) -> None:
    """Fired after every status change, so a match can follow its booking."""
    for hook in _booking_transition_hooks:
        hook(booking=booking, **context)
