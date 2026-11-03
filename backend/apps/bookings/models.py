"""Bookings (DOMAIN §5).

A booking reserves one ground for one time range. The rule that matters most is that
**double booking is impossible at the database level**, not merely unlikely: two requests
racing for the same slot both pass any `SELECT ... WHERE overlaps` check, and only a
constraint can break the tie. That is what ``ExclusionConstraint`` below does — Postgres
rejects the second insert, and ``create_booking`` turns the IntegrityError into "that
slot was just taken".

The constraint needs `btree_gist` (for the equality operator on a uuid column inside a
GiST index); the extension is created in ``apps/core/migrations/0001_extensions.py``.

``status`` is a state machine. Every transition is one function in ``services.py`` that
validates the from-state, writes the new one, and records a ``BookingEvent`` — so a
booking's history is always reconstructable, and support can see who did what.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.sports.models import Sport, SportFormat
from apps.turfs.models import Ground


class BookingStatus(models.TextChoices):
    RESERVED = "reserved", _("Reserved")
    CONFIRMED = "confirmed", _("Confirmed")
    PAID = "paid", _("Paid")
    COMPLETED = "completed", _("Completed")
    EXPIRED = "expired", _("Expired")
    CANCELLED = "cancelled", _("Cancelled")
    NO_SHOW = "no_show", _("No-show")


#: Statuses that hold a slot. The exclusion constraint applies to exactly these, so a
#: cancelled or expired booking frees its slot immediately for someone else.
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.RESERVED,
    BookingStatus.CONFIRMED,
    BookingStatus.PAID,
    BookingStatus.COMPLETED,
)

#: Statuses from which nothing further can happen.
TERMINAL_BOOKING_STATUSES = (
    BookingStatus.COMPLETED,
    BookingStatus.EXPIRED,
    BookingStatus.CANCELLED,
    BookingStatus.NO_SHOW,
)


class BookingMode(models.TextChoices):
    INDIVIDUAL = "individual", _("Individual")
    GROUP = "group", _("Group")


class BookingVisibility(models.TextChoices):
    PUBLIC = "public", _("Public — looking for players")
    PRIVATE = "private", _("Private")


class Booking(BaseModel):
    ground = models.ForeignKey(Ground, on_delete=models.PROTECT, related_name="bookings")
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        help_text="The account that made the booking, including a staff walk-in.",
    )
    booked_for_name = models.CharField(
        _("walk-in name"),
        max_length=120,
        blank=True,
        help_text="Set when staff book on behalf of someone with no account.",
    )
    booked_for_phone = models.CharField(_("walk-in phone"), max_length=32, blank=True)

    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="bookings")
    sport_format = models.ForeignKey(SportFormat, on_delete=models.PROTECT, related_name="bookings")
    time_range = DateTimeRangeField(
        _("time range"),
        help_text="Half-open [start, end): back-to-back slots do not collide.",
    )
    price = models.DecimalField(
        _("price"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="BDT, resolved from the ground's price rules when the booking is made.",
    )
    price_label = models.CharField(_("price label"), max_length=40, blank=True)

    mode = models.CharField(
        _("mode"), max_length=12, choices=BookingMode.choices, default=BookingMode.INDIVIDUAL
    )
    squad = models.ForeignKey(
        "matches.Squad",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
        help_text="Set for a group booking (DOMAIN §6).",
    )
    visibility = models.CharField(
        _("visibility"),
        max_length=8,
        choices=BookingVisibility.choices,
        default=BookingVisibility.PUBLIC,
        help_text="DECISIONS D2: the booker chooses. Public bookings reach the match board.",
    )

    status = models.CharField(
        _("status"),
        max_length=12,
        choices=BookingStatus.choices,
        default=BookingStatus.RESERVED,
        db_index=True,
    )
    expires_at = models.DateTimeField(
        _("reservation expires at"),
        null=True,
        blank=True,
        help_text=(
            "Only while `reserved`: the point at which an unconfirmed slot is released "
            "(DECISIONS D3)."
        ),
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_bookings",
    )
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    auto_confirmed = models.BooleanField(
        _("auto-confirmed"),
        default=False,
        help_text="True when the player's record met the bar in DECISIONS D3.",
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancel_reason = models.CharField(_("cancellation reason"), max_length=200, blank=True)
    was_late_cancel = models.BooleanField(
        _("late cancellation"),
        default=False,
        help_text="Cancelled inside the turf's free window, so it counted against reliability.",
    )
    notes = models.TextField(_("notes"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("booking")
        verbose_name_plural = _("bookings")
        ordering = ["-created_at"]
        constraints = [
            # The whole point of the phase: Postgres, not application code, is what makes
            # a double booking impossible. Restricted to the statuses that actually hold
            # the slot, so cancelling frees it at once.
            ExclusionConstraint(
                name="no_overlapping_active_bookings",
                expressions=[
                    ("ground", RangeOperators.EQUAL),
                    ("time_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(status__in=ACTIVE_BOOKING_STATUSES),
            ),
        ]
        indexes = [
            models.Index(fields=["ground", "status"], name="booking_ground_status_idx"),
            models.Index(fields=["booked_by", "-created_at"], name="booking_player_idx"),
            models.Index(fields=["status", "expires_at"], name="booking_expiry_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ground} {self.starts_at:%Y-%m-%d %H:%M} ({self.status})"

    @property
    def starts_at(self):
        return self.time_range.lower

    @property
    def ends_at(self):
        return self.time_range.upper

    @property
    def turf(self):
        return self.ground.turf

    @property
    def is_active(self) -> bool:
        """Holds its slot, so nobody else can take it."""
        return self.status in ACTIVE_BOOKING_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BOOKING_STATUSES

    @property
    def player_name(self) -> str:
        """Who the slot is for: a walk-in name wins over the booking account."""
        return self.booked_for_name or self.booked_by.full_name or self.booked_by.email


class BookingEvent(BaseModel):
    """One transition in a booking's life (CLAUDE.md: every state change records an event).

    Append-only. It answers "who confirmed this, and when" long after the booking row
    itself has moved on, which is most of what support ever needs.
    """

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(
        _("from"), max_length=12, choices=BookingStatus.choices, blank=True
    )
    to_status = models.CharField(_("to"), max_length=12, choices=BookingStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_events",
        help_text="Null when the system did it — expiry and completion run unattended.",
    )
    note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("booking event")
        verbose_name_plural = _("booking events")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.from_status or '—'} -> {self.to_status}"
