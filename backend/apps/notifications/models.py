"""In-app notifications (DOMAIN §11).

Every request, approval, invite, booking change, scorecard action, MOTM result and order
update lands here, so the model is deliberately generic: a ``kind``, a rendered title and
body, and a ``data`` blob carrying whatever the UI needs to build a link.

Rendering happens **once, at creation**. A notification is a record of what the player was
told at the time — re-rendering it later from live data would silently rewrite history
when a booking is cancelled or a price changes.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class NotificationKind(models.TextChoices):
    """Every notification type in the product, added to as phases land."""

    # Phase 03 — bookings
    BOOKING_CREATED = "booking_created", _("Booking created")
    BOOKING_PENDING_CONFIRMATION = (
        "booking_pending_confirmation",
        _("Booking needs confirmation"),
    )
    BOOKING_CONFIRMED = "booking_confirmed", _("Booking confirmed")
    BOOKING_EXPIRED = "booking_expired", _("Booking expired")
    BOOKING_CANCELLED = "booking_cancelled", _("Booking cancelled")
    BOOKING_PAID = "booking_paid", _("Payment received")
    BOOKING_NO_SHOW = "booking_no_show", _("Marked as a no-show")
    BOOKING_COMPLETED = "booking_completed", _("Booking completed")
    BOOKING_REMINDER = "booking_reminder", _("Booking reminder")

    # Phase 04 — squads and matches
    SQUAD_INVITE = "squad_invite", _("Squad invitation")
    SQUAD_JOINED = "squad_joined", _("Someone joined your squad")
    MATCH_ADDED = "match_added", _("Added to a match")
    MATCH_REMOVED = "match_removed", _("Removed from a match")
    MATCH_PLAYER_LEFT = "match_player_left", _("A player dropped out")
    MATCH_JOIN_REQUEST = "match_join_request", _("Someone wants to join")
    MATCH_JOIN_APPROVED = "match_join_approved", _("You are in")
    MATCH_JOIN_DECLINED = "match_join_declined", _("Request declined")
    MATCH_INVITE = "match_invite", _("Match invitation")
    MATCH_INVITE_PROPOSED = "match_invite_proposed", _("A player was proposed")
    MATCH_INVITE_ACCEPTED = "match_invite_accepted", _("Invitation accepted")
    MATCH_INVITE_DECLINED = "match_invite_declined", _("Invitation declined")

    # Phase 05 — scoring
    SCORECARD_SUBMITTED = "scorecard_submitted", _("Scorecard needs confirming")
    SCORECARD_DISPUTED = "scorecard_disputed", _("Scorecard disputed")
    SCORECARD_LOCKED = "scorecard_locked", _("Scorecard final")
    MOTM_AWARDED = "motm_awarded", _("Man of the match")

    # Phase 07 — inventory
    STOCK_LOW = "stock_low", _("Stock running low")
    RENTAL_OUT = "rental_out", _("Gear taken out")
    RENTAL_OVERDUE = "rental_overdue", _("Gear not returned")

    # Phase 08 — the store
    ORDER_PLACED = "order_placed", _("New order")
    ORDER_ACCEPTED = "order_accepted", _("Order accepted")
    ORDER_READY = "order_ready", _("Order ready for pickup")
    ORDER_ASSIGNED = "order_assigned", _("Delivery assigned")
    ORDER_DELIVERED = "order_delivered", _("Order delivered")
    ORDER_CANCELLED = "order_cancelled", _("Order cancelled")
    ORDER_CUTOFF_SOON = "order_cutoff_soon", _("Order before the cutoff")


class Notification(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(_("kind"), max_length=48, choices=NotificationKind.choices)
    title = models.CharField(_("title"), max_length=160)
    body = models.TextField(_("body"), blank=True)
    data = models.JSONField(
        _("data"),
        default=dict,
        blank=True,
        help_text="Whatever the UI needs to link onwards, e.g. {'booking_id': ...}.",
    )
    url = models.CharField(
        _("link"),
        max_length=300,
        blank=True,
        help_text="Relative path the notification opens, e.g. /bookings/<id>.",
    )
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    emailed_at = models.DateTimeField(_("emailed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            # The bell polls "unread for me" on every page, so that is the index.
            models.Index(fields=["user", "read_at", "-created_at"], name="notification_inbox_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} -> {self.user}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
