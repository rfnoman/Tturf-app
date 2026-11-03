"""Slot availability for a ground on a date (DOMAIN §4).

    availability = operating hours − closures − active bookings, sliced by slot_minutes

Bookings do not exist until Phase 03, and `apps.turfs` must not import `apps.bookings`
(the dependency runs the other way). So the third term is a **registry**: Phase 03's
`BookingsConfig.ready()` registers a provider, and until then the list is empty and every
open slot reads as free. Nothing here changes when that happens — which is the point, per
the phase brief: "write the selector so it already queries them via an interface".

Everything is computed in Dhaka local time and returned as aware UTC datetimes, because a
turf's "18:00–02:00 Friday" is a statement about local wall-clock time, not UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Protocol

from django.utils import timezone

from apps.core.utils import DHAKA

from .models import Closure, Ground, OperatingHours, PriceRule


@dataclass(frozen=True)
class TimeRange:
    """A half-open interval ``[start, end)`` of aware datetimes."""

    start: datetime
    end: datetime

    def overlaps(self, other: TimeRange) -> bool:
        # Half-open, so touching intervals (end == other.start) do not overlap. That is
        # what lets back-to-back slots both be bookable.
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Slot:
    """One bookable slot, priced and resolved."""

    start: datetime
    end: datetime
    price: Decimal | None
    label: str
    available: bool
    reason: str = ""

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


class BookedRangeProvider(Protocol):
    """What Phase 03 registers: the ranges on this ground that are already taken."""

    def __call__(self, *, ground: Ground, start: datetime, end: datetime) -> list[TimeRange]: ...


_booked_range_providers: list[BookedRangeProvider] = []


def register_booked_range_provider(provider: BookedRangeProvider) -> None:
    """Let another app contribute ranges that make a slot unavailable.

    Called from an ``AppConfig.ready()``, which can run more than once under the
    autoreloader, so registering the same callable twice is a no-op.
    """
    if provider not in _booked_range_providers:
        _booked_range_providers.append(provider)


def clear_booked_range_providers() -> None:
    """Test hook: drop every registered provider."""
    _booked_range_providers.clear()


def booked_ranges(*, ground: Ground, start: datetime, end: datetime) -> list[TimeRange]:
    ranges: list[TimeRange] = []
    for provider in _booked_range_providers:
        ranges.extend(provider(ground=ground, start=start, end=end))
    return ranges


def _aware(day: date, moment: time) -> datetime:
    """Combine a Dhaka-local date and time into an aware datetime."""
    return datetime.combine(day, moment, tzinfo=DHAKA)


def opening_windows(*, turf_hours: list[OperatingHours], day: date) -> list[TimeRange]:
    """The turf's open windows for the Dhaka-local calendar date ``day``.

    Two sources contribute:

    1. rows for ``day``'s own weekday, and
    2. rows for the **previous** weekday that cross midnight — a Friday 18:00–02:00 row
       puts 00:00–02:00 on Saturday, and dropping it would make the small hours
       unbookable even though the turf is open and staffed.
    """
    windows: list[TimeRange] = []
    previous = day - timedelta(days=1)

    for hours in turf_hours:
        if hours.weekday == day.weekday():
            start = _aware(day, hours.open_time)
            end = _aware(
                day if not hours.crosses_midnight else day + timedelta(days=1), hours.close_time
            )
            if end > start:
                windows.append(TimeRange(start, end))
        if hours.weekday == previous.weekday() and hours.crosses_midnight:
            # The tail of yesterday's window that lands on `day`.
            start = _aware(previous, hours.open_time)
            end = _aware(day, hours.close_time)
            tail = TimeRange(max(start, _aware(day, time.min)), end)
            if tail.end > tail.start:
                windows.append(tail)

    return sorted(windows, key=lambda w: w.start)


def price_for(*, rules: list[PriceRule], start: datetime) -> tuple[Decimal | None, str]:
    """Price a slot by its start, using the most specific matching rule.

    Matching is on the Dhaka-local weekday and time of the slot's **start**: a slot
    belongs to the band it begins in, so a 90-minute booking that straddles the peak
    boundary is not silently repriced halfway through.
    """
    local = start.astimezone(DHAKA)
    weekday = local.weekday()
    moment = local.time()

    matches = [
        rule for rule in rules if rule.covers_weekday(weekday) and _time_in_window(moment, rule)
    ]
    if not matches:
        return None, ""

    best = min(matches, key=lambda rule: rule.specificity)
    return best.price, best.label


def _time_in_window(moment: time, rule: PriceRule) -> bool:
    if rule.crosses_midnight:
        # e.g. 22:00–02:00 matches 23:30 and 00:30, but not 12:00.
        return moment >= rule.start_time or moment < rule.end_time
    return rule.start_time <= moment < rule.end_time


def get_availability(*, ground: Ground, day: date, include_past: bool = False) -> list[Slot]:
    """Every slot on ``ground`` for the Dhaka-local date ``day``.

    Unavailable slots are returned too, carrying a ``reason`` — the UI shows a greyed-out
    slot rather than a gap, so a player can see the turf is busy rather than assume it is
    shut. Past slots are dropped unless ``include_past``.
    """
    turf_hours = list(ground.turf.operating_hours.all())
    windows = opening_windows(turf_hours=turf_hours, day=day)
    if not windows:
        return []

    rules = list(ground.price_rules.all())
    span_start = min(window.start for window in windows)
    span_end = max(window.end for window in windows)

    closures = [
        TimeRange(closure.starts_at, closure.ends_at)
        for closure in Closure.objects.filter(turf_id=ground.turf_id).filter(
            starts_at__lt=span_end, ends_at__gt=span_start
        )
        # A turf-wide closure has no ground; a ground-specific one must match.
        if closure.ground_id in (None, ground.id)
    ]
    taken = booked_ranges(ground=ground, start=span_start, end=span_end)
    now = timezone.now()

    slots: list[Slot] = []
    length = timedelta(minutes=ground.slot_minutes)
    for window in windows:
        cursor = window.start
        # Only whole slots are offered: a 45-minute remainder at closing time is not
        # bookable, and offering it would let a match run past the turf's closing hour.
        while cursor + length <= window.end:
            slot_range = TimeRange(cursor, cursor + length)
            price, label = price_for(rules=rules, start=cursor)

            reason = ""
            if not include_past and slot_range.start < now:
                cursor += length
                continue
            if any(slot_range.overlaps(closure) for closure in closures):
                reason = "closed"
            elif any(slot_range.overlaps(booking) for booking in taken):
                reason = "booked"
            elif price is None:
                # Should be unreachable on an active ground; activation enforces coverage.
                reason = "unpriced"

            slots.append(
                Slot(
                    start=slot_range.start,
                    end=slot_range.end,
                    price=price,
                    label=label,
                    available=not reason,
                    reason=reason,
                )
            )
            cursor += length

    return slots


def uncovered_minutes(*, ground: Ground) -> list[tuple[int, time, time]]:
    """Open minutes on this ground that no price rule covers.

    Returned as ``(weekday, from, until)`` gaps so an owner can be told exactly what to
    fix. Empty means the ground may be activated (DOMAIN §4: "a ground must have full
    coverage of its operating hours before it can be activated").
    """
    rules = list(ground.price_rules.all())
    gaps: list[tuple[int, time, time]] = []

    for hours in ground.turf.operating_hours.all():
        # Walk the window a minute at a time in local terms. Windows are hours long, so
        # this is cheap, and it handles crossing midnight without interval arithmetic.
        start = hours.open_time.hour * 60 + hours.open_time.minute
        close = hours.close_time.hour * 60 + hours.close_time.minute
        total = (close - start) if not hours.crosses_midnight else (24 * 60 - start + close)

        gap_start: int | None = None
        for offset in range(total):
            absolute = (start + offset) % (24 * 60)
            weekday = (hours.weekday + (start + offset) // (24 * 60)) % 7
            moment = time(hour=absolute // 60, minute=absolute % 60)
            covered = any(
                rule.covers_weekday(weekday) and _time_in_window(moment, rule) for rule in rules
            )
            if not covered and gap_start is None:
                gap_start = start + offset
            elif covered and gap_start is not None:
                gaps.append(_as_gap(hours.weekday, gap_start, start + offset))
                gap_start = None
        if gap_start is not None:
            gaps.append(_as_gap(hours.weekday, gap_start, start + total))

    return gaps


def _as_gap(weekday: int, start_minute: int, end_minute: int) -> tuple[int, time, time]:
    day_offset = start_minute // (24 * 60)
    start = start_minute % (24 * 60)
    end = end_minute % (24 * 60)
    return (
        (weekday + day_offset) % 7,
        time(hour=start // 60, minute=start % 60),
        time(hour=end // 60, minute=end % 60),
    )


__all__ = [
    "BookedRangeProvider",
    "Slot",
    "TimeRange",
    "booked_ranges",
    "clear_booked_range_providers",
    "get_availability",
    "opening_windows",
    "price_for",
    "register_booked_range_provider",
    "uncovered_minutes",
]
