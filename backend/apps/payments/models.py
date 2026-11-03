"""Payments (DOMAIN §5, §12).

Cash is the only method in Phase 03; SSLCommerz and bKash arrive in Phase 10 (D8), and
the ``LedgerEntry`` that splits each payment between platform and turf comes with them.
The shape is built for that now so Phase 10 adds providers rather than reshaping rows.

A payment points at **either** a booking or (from Phase 08) an order, never both. The
two nullable FKs plus a check constraint are deliberate: a `GenericForeignKey` would buy
nothing here beyond losing referential integrity and join-ability.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class PaymentMethod(models.TextChoices):
    CASH = "cash", _("Cash")
    SSLCOMMERZ = "sslcommerz", _("SSLCommerz")
    BKASH = "bkash", _("bKash")


class PaymentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PAID = "paid", _("Paid")
    REFUNDED = "refunded", _("Refunded")
    FAILED = "failed", _("Failed")


class Payment(BaseModel):
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payments",
    )
    # Phase 08 adds `order`; the check constraint below already expects it to be exclusive.
    method = models.CharField(
        _("method"), max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="BDT. Money is always Decimal (CLAUDE.md).",
    )
    status = models.CharField(
        _("status"), max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collected_payments",
        help_text="The staff member who took the cash.",
    )
    collected_at = models.DateTimeField(_("collected at"), null=True, blank=True)
    reference = models.CharField(
        _("reference"),
        max_length=120,
        blank=True,
        help_text="Provider transaction id from Phase 10. Empty for cash.",
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(booking__isnull=False),
                name="payment_has_a_target",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "method"], name="payment_status_method_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_method_display()} ৳{self.amount} ({self.status})"

    @property
    def is_settled(self) -> bool:
        return self.status == PaymentStatus.PAID
