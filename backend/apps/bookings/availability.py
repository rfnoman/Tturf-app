"""Plugging bookings into Phase 02's availability selector.

``apps.turfs`` must not import ``apps.bookings`` — the dependency runs the other way —
so Phase 02 left a registry (DECISIONS D25) and this is what fills it. Registered from
``BookingsConfig.ready()``, which is why nothing in ``apps/turfs`` changed when bookings
arrived.
"""

from __future__ import annotations

from datetime import datetime

from psycopg.types.range import TimestamptzRange

from apps.turfs.availability import TimeRange
from apps.turfs.models import Ground

from .models import ACTIVE_BOOKING_STATUSES, Booking


def booked_ranges(*, ground: Ground, start: datetime, end: datetime) -> list[TimeRange]:
    """The ranges on this ground already held by an active booking.

    Only the statuses that actually hold a slot count, so a cancelled or expired booking
    frees its slot the moment it moves — the same set the exclusion constraint uses.
    """
    bookings = Booking.objects.filter(
        ground=ground,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_range__overlap=TimestamptzRange(start, end),
    ).only("time_range")

    return [TimeRange(booking.time_range.lower, booking.time_range.upper) for booking in bookings]
