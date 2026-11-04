"""Booking business logic (DOMAIN §5, DECISIONS D3).

``Booking.status`` is a state machine:

    reserved -> confirmed -> paid -> completed
    reserved -> expired                      (not confirmed in time; slot released)
    reserved|confirmed -> cancelled          (by player or staff, with a reason)
    confirmed|paid -> no_show                (marked by staff after start + grace)

Every transition is one function here. Each validates the from-state, writes the new one,
records a ``BookingEvent``, and notifies whoever needs to know — so nothing else in the
codebase ever assigns ``booking.status`` (CLAUDE.md).

Reliability (DOMAIN §5) moves only through :func:`adjust_reliability`, with the deltas
configurable in settings.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from psycopg.types.range import TimestamptzRange

from apps.core.utils import DHAKA, now
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify, notify_many
from apps.players.models import PlayerProfile
from apps.players.services import get_or_create_profile
from apps.turfs.availability import get_availability
from apps.turfs.models import Ground, Turf, TurfMembership

from .hooks import booking_created, booking_transitioned
from .models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    BookingEvent,
    BookingMode,
    BookingStatus,
    BookingVisibility,
)

logger = logging.getLogger(__name__)


class SlotTakenError(ValidationError):
    """Raised when the exclusion constraint rejects an overlapping booking."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def record_event(
    *, booking: Booking, from_status: str, to_status: str, actor=None, note: str = ""
) -> BookingEvent:
    return BookingEvent.objects.create(
        booking=booking,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        note=note[:300],
    )


def _require(booking: Booking, allowed: tuple[str, ...], action: str) -> None:
    if booking.status not in allowed:
        raise ValidationError(
            {"status": f"A {booking.get_status_display().lower()} booking cannot be {action}."}
        )


def _context(booking: Booking) -> dict:
    """The placeholders every booking notification template uses."""
    local = booking.starts_at.astimezone(DHAKA)
    return {
        "turf": booking.turf.name,
        "ground": booking.ground.name,
        "when": local.strftime("%a %d %b, %H:%M"),
        "price": f"৳{booking.price}",
        "player": booking.player_name,
        "expires": (
            booking.expires_at.astimezone(DHAKA).strftime("%H:%M")
            if booking.expires_at
            else "the slot starts"
        ),
        "reason": booking.cancel_reason or "",
    }


def _booking_url(booking: Booking) -> str:
    return f"/bookings/{booking.id}"


def turf_staff_users(turf: Turf) -> list:
    """Everyone who can act on a booking at this turf."""
    return [
        membership.user
        for membership in turf.memberships.filter(
            status=TurfMembership.Status.ACTIVE, user__isnull=False
        ).select_related("user")
    ]


def _notify_player(booking: Booking, kind: str) -> None:
    """Tell whoever the booking belongs to.

    For a walk-in taken at the counter that is the staff member who entered it, which is
    the right person: they are the one who has to tell the customer.
    """
    notify(
        user=booking.booked_by,
        kind=kind,
        url=_booking_url(booking),
        data={"booking_id": str(booking.id)},
        **_context(booking),
    )


# ---------------------------------------------------------------------------
# Reliability (DOMAIN §5)
# ---------------------------------------------------------------------------
@transaction.atomic
def adjust_reliability(*, profile: PlayerProfile, delta: int, reason: str = "") -> PlayerProfile:
    """Move a player's reliability score, clamped to 0–100.

    The single writer of ``reliability_score``: a no-show and a late cancel must not be
    able to drift apart from the configured deltas.
    """
    ceiling = int(settings.RELIABILITY_MAX)
    profile.reliability_score = max(0, min(ceiling, profile.reliability_score + delta))
    profile.save(update_fields=["reliability_score", "updated_at"])
    logger.info(
        "Reliability adjusted",
        extra={"profile": str(profile.id), "delta": delta, "reason": reason},
    )
    return profile


def completed_booking_count(user) -> int:
    return Booking.objects.filter(booked_by=user, status=BookingStatus.COMPLETED).count()


def should_auto_confirm(*, user, turf: Turf) -> bool:
    """DECISIONS D3: does this player's record earn an instant confirmation?

    All three must hold — the turf allows it, the player has enough completed bookings,
    and their reliability is above the bar. Anything else waits for staff.
    """
    if not turf.auto_confirm_enabled:
        return False

    profile = get_or_create_profile(user)
    return completed_booking_count(user) >= int(
        settings.BOOKING_AUTO_CONFIRM_MIN_COMPLETED
    ) and profile.reliability_score >= int(settings.BOOKING_AUTO_CONFIRM_MIN_RELIABILITY)


def confirmation_deadline(*, start):
    """When an unconfirmed reservation is released (DECISIONS D3).

    Two hours from now, **or** an hour before kickoff — whichever comes first, because a
    slot released after the game would have started helps nobody.
    """
    window = now() + timedelta(hours=float(settings.BOOKING_CONFIRM_WINDOW_HOURS))
    cutoff = start - timedelta(hours=float(settings.BOOKING_CONFIRM_CUTOFF_HOURS_BEFORE_START))
    return min(window, cutoff)


# ---------------------------------------------------------------------------
# Creating a booking
# ---------------------------------------------------------------------------
def resolve_slot(*, ground: Ground, start) -> tuple:
    """Find the offered slot beginning at ``start``, and its price.

    Deliberately re-derived from ``get_availability`` rather than trusting the client:
    it is the same function the slot grid rendered from, so a booking can only ever be
    made for a slot the turf actually offers, at the price it actually advertised.
    """
    local_day = start.astimezone(DHAKA).date()
    for slot in get_availability(ground=ground, day=local_day, include_past=True):
        if slot.start == start:
            return slot
    raise ValidationError({"start": "That slot is not offered on this ground."})


@transaction.atomic
def create_booking(
    *,
    user,
    ground: Ground,
    start,
    sport_format,
    mode: str = BookingMode.INDIVIDUAL,
    visibility: str = BookingVisibility.PUBLIC,
    notes: str = "",
    booked_for_name: str = "",
    booked_for_phone: str = "",
    squad=None,
    actor=None,
) -> Booking:
    """Book a slot, applying DECISIONS D3 to decide whether it confirms immediately.

    Raises :class:`SlotTakenError` when the exclusion constraint rejects the insert —
    which is the *expected* outcome when two players press Book at the same moment, not
    an exceptional one.
    """
    turf = ground.turf
    if turf.status != Turf.Status.APPROVED:
        raise ValidationError({"ground": "This turf is not accepting bookings."})
    if not ground.is_active:
        raise ValidationError({"ground": "This ground is not bookable."})

    if sport_format not in ground.sport_formats.all():
        raise ValidationError({"sport_format": f"{ground.name} does not host that format."})

    if start <= now():
        raise ValidationError({"start": "That slot has already started."})

    horizon = now() + timedelta(days=int(settings.BOOKING_HORIZON_DAYS))
    if start > horizon:
        raise ValidationError(
            {"start": f"Bookings open {settings.BOOKING_HORIZON_DAYS} days ahead."}
        )

    slot = resolve_slot(ground=ground, start=start)
    if slot.price is None:
        raise ValidationError({"start": "That slot has no price set."})
    if not slot.available and slot.reason == "closed":
        raise ValidationError({"start": "The turf is closed then."})

    # One player, one slot: a double booking across *different* grounds is still a
    # person who cannot be in two places at once.
    clash = Booking.objects.filter(
        booked_by=user,
        status__in=ACTIVE_BOOKING_STATUSES,
        time_range__overlap=TimestamptzRange(slot.start, slot.end),
    ).exists()
    if clash:
        raise ValidationError({"start": "You already have a booking at that time."})

    if mode == BookingMode.GROUP:
        if squad is None:
            raise ValidationError({"squad": "Choose a squad for a group booking."})
        # Only somebody actually in the squad may book in its name.
        from apps.matches.services import is_squad_member

        if not is_squad_member(squad=squad, user=user):
            raise ValidationError({"squad": "You are not in that squad."})
    elif squad is not None:
        raise ValidationError({"squad": "Only a group booking has a squad."})

    auto = should_auto_confirm(user=user, turf=turf)
    status = BookingStatus.CONFIRMED if auto else BookingStatus.RESERVED

    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                ground=ground,
                booked_by=user,
                booked_for_name=booked_for_name.strip(),
                booked_for_phone=booked_for_phone.strip(),
                sport=sport_format.sport,
                sport_format=sport_format,
                time_range=TimestamptzRange(slot.start, slot.end),
                price=Decimal(slot.price),
                price_label=slot.label,
                mode=mode,
                visibility=visibility,
                notes=notes.strip(),
                squad=squad,
                status=status,
                auto_confirmed=auto,
                confirmed_at=now() if auto else None,
                expires_at=None if auto else confirmation_deadline(start=slot.start),
            )
    except IntegrityError as exc:
        # The exclusion constraint is the only thing that can reject this insert, and it
        # means somebody else got the slot in the microseconds since availability loaded.
        logger.info(
            "Slot taken while booking",
            extra={"ground": str(ground.id), "start": slot.start.isoformat()},
        )
        raise SlotTakenError({"start": "That slot was just taken. Please choose another."}) from exc

    record_event(
        booking=booking,
        from_status="",
        to_status=booking.status,
        actor=actor or user,
        note="Auto-confirmed" if auto else "Awaiting confirmation",
    )

    # Phase 04 creates the match here. Inside the transaction on purpose: a booking with
    # no match is not a state the rest of the app knows how to handle.
    booking_created(booking=booking, squad=squad)

    if auto:
        _notify_player(booking, NotificationKind.BOOKING_CONFIRMED)
    else:
        _notify_player(booking, NotificationKind.BOOKING_CREATED)
        notify_many(
            users=turf_staff_users(turf),
            kind=NotificationKind.BOOKING_PENDING_CONFIRMATION,
            url=_booking_url(booking),
            data={"booking_id": str(booking.id)},
            **_context(booking),
        )

    logger.info(
        "Booking created",
        extra={"booking": str(booking.id), "status": booking.status, "auto": auto},
    )
    return booking


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
@transaction.atomic
def confirm_booking(*, booking: Booking, actor=None, note: str = "") -> Booking:
    """``reserved -> confirmed``: staff accept the reservation."""
    _require(booking, (BookingStatus.RESERVED,), "confirmed")

    previous = booking.status
    booking.status = BookingStatus.CONFIRMED
    booking.confirmed_by = actor
    booking.confirmed_at = now()
    booking.expires_at = None
    booking.save(
        update_fields=["status", "confirmed_by", "confirmed_at", "expires_at", "updated_at"]
    )

    record_event(
        booking=booking,
        from_status=previous,
        to_status=booking.status,
        actor=actor,
        note=note,
    )
    booking_transitioned(booking=booking, from_status=previous)
    _notify_player(booking, NotificationKind.BOOKING_CONFIRMED)
    return booking


@transaction.atomic
def expire_booking(*, booking: Booking) -> Booking:
    """``reserved -> expired``: nobody confirmed in time, so the slot is released.

    Run unattended by Celery beat, hence no actor.
    """
    _require(booking, (BookingStatus.RESERVED,), "expired")

    previous = booking.status
    booking.status = BookingStatus.EXPIRED
    booking.expires_at = None
    booking.save(update_fields=["status", "expires_at", "updated_at"])

    record_event(
        booking=booking,
        from_status=previous,
        to_status=booking.status,
        note="Not confirmed before the deadline",
    )
    booking_transitioned(booking=booking, from_status=previous)
    _notify_player(booking, NotificationKind.BOOKING_EXPIRED)
    logger.info("Booking expired", extra={"booking": str(booking.id)})
    return booking


def is_late_cancellation(booking: Booking) -> bool:
    """Inside the turf's free-cancellation window (DOMAIN §5)."""
    free_until = booking.starts_at - timedelta(hours=booking.turf.cancellation_free_hours)
    return now() > free_until


@transaction.atomic
def cancel_booking(
    *, booking: Booking, actor=None, reason: str = "", by_staff: bool = False
) -> Booking:
    """``reserved|confirmed|paid -> cancelled``.

    A late cancellation by the **player** costs reliability (DOMAIN §5); one made by the
    turf does not — the player did nothing wrong, and penalising them for the venue's
    change of plan would be both unfair and a reason to stop using the app.
    """
    _require(
        booking, (BookingStatus.RESERVED, BookingStatus.CONFIRMED, BookingStatus.PAID), "cancelled"
    )

    late = (not by_staff) and is_late_cancellation(booking)

    previous = booking.status
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_by = actor
    booking.cancelled_at = now()
    booking.cancel_reason = (reason or "").strip()[:200]
    booking.was_late_cancel = late
    booking.expires_at = None
    booking.save(
        update_fields=[
            "status",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            "was_late_cancel",
            "expires_at",
            "updated_at",
        ]
    )

    record_event(
        booking=booking,
        from_status=previous,
        to_status=booking.status,
        actor=actor,
        note=("Late cancellation. " + booking.cancel_reason).strip(),
    )
    booking_transitioned(booking=booking, from_status=previous)

    if late:
        adjust_reliability(
            profile=get_or_create_profile(booking.booked_by),
            delta=int(settings.RELIABILITY_LATE_CANCEL_DELTA),
            reason="late_cancel",
        )

    _notify_player(booking, NotificationKind.BOOKING_CANCELLED)
    if by_staff is False:
        notify_many(
            users=turf_staff_users(booking.turf),
            kind=NotificationKind.BOOKING_CANCELLED,
            url=_booking_url(booking),
            data={"booking_id": str(booking.id)},
            **_context(booking),
        )
    return booking


@transaction.atomic
def mark_paid(*, booking: Booking, actor=None, amount=None, record_payment: bool = True) -> Booking:
    """``confirmed -> paid``.

    `record_payment` is False when the money arrived through a gateway: Phase 10 has
    already written that `Payment` row and posted the ledger, and recording a second,
    cash one here would double the turf's takings.
    """
    _require(booking, (BookingStatus.CONFIRMED,), "marked paid")

    if record_payment:
        from apps.payments.services import record_cash_payment

        record_cash_payment(booking=booking, collected_by=actor, amount=amount)

    previous = booking.status
    booking.status = BookingStatus.PAID
    booking.save(update_fields=["status", "updated_at"])

    record_event(booking=booking, from_status=previous, to_status=booking.status, actor=actor)
    booking_transitioned(booking=booking, from_status=previous)
    _notify_player(booking, NotificationKind.BOOKING_PAID)
    return booking


@transaction.atomic
def mark_no_show(*, booking: Booking, actor=None, note: str = "") -> Booking:
    """``confirmed|paid -> no_show``, only once the grace period after kickoff has passed.

    The grace period is the point: marking a no-show at the scheduled start would punish
    a player stuck in Dhaka traffic who is three minutes away.
    """
    _require(booking, (BookingStatus.CONFIRMED, BookingStatus.PAID), "marked as a no-show")

    grace = booking.starts_at + timedelta(minutes=int(settings.BOOKING_NO_SHOW_GRACE_MINUTES))
    if now() < grace:
        raise ValidationError(
            {
                "status": (
                    f"Wait until {settings.BOOKING_NO_SHOW_GRACE_MINUTES} minutes after "
                    "the start before marking a no-show."
                )
            }
        )

    previous = booking.status
    booking.status = BookingStatus.NO_SHOW
    booking.save(update_fields=["status", "updated_at"])

    record_event(
        booking=booking,
        from_status=previous,
        to_status=booking.status,
        actor=actor,
        note=note,
    )
    booking_transitioned(booking=booking, from_status=previous)
    adjust_reliability(
        profile=get_or_create_profile(booking.booked_by),
        delta=int(settings.RELIABILITY_NO_SHOW_DELTA),
        reason="no_show",
    )
    _notify_player(booking, NotificationKind.BOOKING_NO_SHOW)
    return booking


@transaction.atomic
def complete_booking(*, booking: Booking, actor=None) -> Booking:
    """``paid -> completed``, once the slot has ended.

    Completion is what earns reliability back (DOMAIN §5) and, from Phase 04, what
    creates the match whose scorecard drives ratings.
    """
    _require(booking, (BookingStatus.PAID,), "completed")
    if now() < booking.ends_at:
        raise ValidationError({"status": "The slot has not finished yet."})

    previous = booking.status
    booking.status = BookingStatus.COMPLETED
    booking.save(update_fields=["status", "updated_at"])

    record_event(booking=booking, from_status=previous, to_status=booking.status, actor=actor)
    booking_transitioned(booking=booking, from_status=previous)
    adjust_reliability(
        profile=get_or_create_profile(booking.booked_by),
        delta=int(settings.RELIABILITY_COMPLETED_MATCH_DELTA),
        reason="completed_booking",
    )
    _notify_player(booking, NotificationKind.BOOKING_COMPLETED)
    return booking


# ---------------------------------------------------------------------------
# Batch jobs (Celery beat)
# ---------------------------------------------------------------------------
def expire_overdue_bookings() -> int:
    """Release every reservation past its deadline. Returns how many."""
    overdue = Booking.objects.filter(
        status=BookingStatus.RESERVED, expires_at__isnull=False, expires_at__lte=now()
    )
    count = 0
    for booking in overdue:
        try:
            expire_booking(booking=booking)
        except ValidationError:
            # Raced with a staff confirmation; the confirmation wins.
            continue
        count += 1
    return count


def complete_finished_bookings() -> int:
    """Close out paid bookings whose slot has ended. Returns how many."""
    finished = Booking.objects.filter(status=BookingStatus.PAID).filter(
        Q(time_range__endswith__lte=now())
    )
    count = 0
    for booking in finished:
        try:
            complete_booking(booking=booking)
        except ValidationError:
            continue
        count += 1
    return count
