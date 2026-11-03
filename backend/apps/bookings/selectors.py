"""Read-side queries for bookings (CLAUDE.md)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import Prefetch, Q, QuerySet
from psycopg.types.range import TimestamptzRange

from apps.core.utils import DHAKA, now
from apps.payments.models import Payment
from apps.turfs.models import Turf, TurfMembership

from .models import ACTIVE_BOOKING_STATUSES, Booking, BookingEvent, BookingStatus


def _with_related(queryset: QuerySet[Booking]) -> QuerySet[Booking]:
    return queryset.select_related(
        "ground", "ground__turf", "sport", "sport_format", "booked_by", "confirmed_by"
    ).prefetch_related(
        Prefetch("events", queryset=BookingEvent.objects.select_related("actor")),
        Prefetch("payments", queryset=Payment.objects.select_related("collected_by")),
    )


def bookings_for_player(user) -> QuerySet[Booking]:
    return _with_related(Booking.objects.filter(booked_by=user))


def upcoming_for_player(user) -> QuerySet[Booking]:
    """Still to be played: an active booking whose slot has not finished."""
    return (
        bookings_for_player(user)
        .filter(status__in=ACTIVE_BOOKING_STATUSES, time_range__endswith__gt=now())
        .order_by("time_range")
    )


def past_for_player(user) -> QuerySet[Booking]:
    """Everything else — finished, cancelled, expired or missed."""
    return (
        bookings_for_player(user)
        .filter(Q(time_range__endswith__lte=now()) | ~Q(status__in=ACTIVE_BOOKING_STATUSES))
        .order_by("-time_range")
    )


def bookings_for_turf(
    turf: Turf, *, day: date | None = None, status: str | None = None
) -> QuerySet[Booking]:
    """The turf's calendar. ``day`` is a Dhaka-local date, not UTC.

    A booking that runs past midnight belongs to the evening it started in, which is why
    the window is built from the local day and widened by a few hours rather than being
    a naive UTC date filter.
    """
    queryset = _with_related(Booking.objects.filter(ground__turf=turf))

    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=DHAKA)
        # Six hours past midnight covers every turf's after-midnight close.
        end = datetime.combine(day + timedelta(days=1), time(6, 0), tzinfo=DHAKA)
        queryset = queryset.filter(time_range__overlap=TimestamptzRange(start, end))

    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by("time_range")


def pending_confirmation_for_turf(turf: Turf) -> QuerySet[Booking]:
    """The queue staff work through, soonest deadline first."""
    return _with_related(
        Booking.objects.filter(ground__turf=turf, status=BookingStatus.RESERVED)
    ).order_by("expires_at")


def staffed_turf_ids(user) -> list:
    if not user or not user.is_authenticated:
        return []
    return list(
        TurfMembership.objects.filter(user=user, status=TurfMembership.Status.ACTIVE).values_list(
            "turf_id", flat=True
        )
    )


def bookings_visible_to(user) -> QuerySet[Booking]:
    """Everything this user may see: their own, plus every booking at a turf they staff."""
    return _with_related(
        Booking.objects.filter(Q(booked_by=user) | Q(ground__turf_id__in=staffed_turf_ids(user)))
    ).distinct()
