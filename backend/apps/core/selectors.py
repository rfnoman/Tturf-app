"""The numbers that say whether the pilot is working (Phase 11 step 6).

Every one of these is already derivable from rows the app writes; what was missing was
anywhere to read them together. A turf owner has a finance page and an admin has four
separate queues, but nobody could answer "how many bookings yesterday, and how many of
them did somebody actually turn up to".

Deliberately computed on demand rather than stored. These are read a few times a day by
a handful of people, and a nightly rollup table is a second source of truth that goes
quietly wrong — the leaderboards earn that treatment (they are read by everybody, all
day); this does not.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DateTimeField, F, Func, Q, Sum
from django.db.models.functions import TruncDate

from apps.bookings.models import Booking, BookingStatus
from apps.core.utils import DHAKA, dhaka_today
from apps.matches.models import Match
from apps.payments.models import LedgerAccount, LedgerEntry, LedgerEntryType
from apps.players.models import PlayerProfile
from apps.store.models import Order, OrderStatus
from apps.turfs.models import Turf


def _window(days: int) -> tuple[date, date]:
    """`days` whole Dhaka days ending today."""
    until = dhaka_today().date()
    return until - timedelta(days=days - 1), until


def platform_overview(*, days: int = 30) -> dict:
    """One screen's worth of "is this working".

    `no_show_rate` is the one worth explaining: it is counted against bookings that
    *reached* their slot (confirmed or completed), not against every booking ever made,
    because a cancelled booking is not a no-show and including them would flatter the
    number exactly as the business grew.
    """
    since, until = _window(days)
    start = dhaka_today() - timedelta(days=days - 1)

    bookings = Booking.objects.filter(time_range__startswith__gte=start)
    reached_slot = bookings.filter(
        status__in=[
            BookingStatus.CONFIRMED,
            BookingStatus.PAID,
            BookingStatus.COMPLETED,
            BookingStatus.NO_SHOW,
        ]
    )
    reached = reached_slot.count()
    no_shows = reached_slot.filter(status=BookingStatus.NO_SHOW).count()

    # Gross merchandise value: what changed hands, read off the ledger rather than
    # re-derived from bookings and orders, so it cannot disagree with the finance page.
    gmv = LedgerEntry.objects.filter(
        occurred_on__gte=since,
        occurred_on__lte=until,
        account=LedgerAccount.PLATFORM,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    commission = LedgerEntry.objects.filter(
        occurred_on__gte=since,
        occurred_on__lte=until,
        type=LedgerEntryType.COMMISSION,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    return {
        "period_start": since,
        "period_end": until,
        "bookings": bookings.count(),
        "bookings_confirmed": bookings.filter(
            status__in=[BookingStatus.CONFIRMED, BookingStatus.PAID, BookingStatus.COMPLETED]
        ).count(),
        "bookings_cancelled": bookings.filter(status=BookingStatus.CANCELLED).count(),
        "no_shows": no_shows,
        # A percentage of the bookings that actually reached their slot. Zero bookings
        # means zero, not a division error.
        "no_show_rate": round(100 * no_shows / reached, 1) if reached else 0.0,
        "matches": Match.objects.filter(booking__time_range__startswith__gte=start).count(),
        "orders": Order.objects.filter(created_at__gte=start).count(),
        "orders_fulfilled": Order.objects.filter(
            created_at__gte=start,
            status__in=[OrderStatus.DELIVERED, OrderStatus.PICKED_UP],
        ).count(),
        # "Active" is a player who did something, not one who exists: a sign-up that
        # never books is not a user of this app.
        "active_players": PlayerProfile.objects.filter(
            user__bookings__time_range__startswith__gte=start
        )
        .distinct()
        .count(),
        "new_players": PlayerProfile.objects.filter(created_at__gte=start).count(),
        "turfs_live": Turf.objects.filter(status=Turf.Status.APPROVED).count(),
        "turfs_pending": Turf.objects.filter(status=Turf.Status.PENDING_REVIEW).count(),
        "platform_earnings": gmv,
        "commission": commission,
    }


def bookings_per_day(*, days: int = 30) -> list[dict]:
    """A sparkline's worth of data: one row per Dhaka day, including the empty ones.

    Days with no bookings are included on purpose — a chart that silently skips them
    draws a line that looks healthy through an outage.
    """
    start = dhaka_today() - timedelta(days=days - 1)
    rows = (
        Booking.objects.filter(time_range__startswith__gte=start)
        # Two steps on purpose: `TruncDate` walks to the *source field* to check its
        # type and finds the range, so the lower bound has to become a named annotation
        # with a declared output field before it can be truncated.
        .annotate(starts_at=_range_start())
        .annotate(day=TruncDate("starts_at", tzinfo=DHAKA))
        .values("day")
        .annotate(
            total=Count("id"),
            confirmed=Count(
                "id", filter=Q(status__in=[BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            ),
        )
        .order_by("day")
    )
    counted = {row["day"]: row for row in rows}

    since, until = _window(days)
    out = []
    day = since
    while day <= until:
        row = counted.get(day)
        out.append(
            {
                "day": day,
                "total": row["total"] if row else 0,
                "confirmed": row["confirmed"] if row else 0,
            }
        )
        day += timedelta(days=1)
    return out


def _range_start():
    """When a booking starts, as a database expression.

    Postgres' `lower()` on a range comes back untyped as far as the ORM is concerned, so
    the output field has to be declared — and it has to be a *named annotation* before
    `TruncDate` will touch it, because `TruncDate` walks to the source field to check
    its type and finds the range itself.
    """
    return Func(F("time_range"), function="lower", output_field=DateTimeField())


def top_turfs(*, days: int = 30, limit: int = 10) -> list[dict]:
    """Which venues the pilot is actually running on."""
    start = dhaka_today() - timedelta(days=days - 1)
    return list(
        Turf.objects.filter(status=Turf.Status.APPROVED)
        .annotate(
            bookings=Count(
                "grounds__bookings",
                filter=Q(grounds__bookings__time_range__startswith__gte=start),
                distinct=True,
            )
        )
        .filter(bookings__gt=0)
        .order_by("-bookings")[:limit]
        .values("name", "slug", "area", "bookings")
    )
