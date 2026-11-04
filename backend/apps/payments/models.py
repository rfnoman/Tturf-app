"""Payments (DOMAIN §5, §12).

Cash is the only method in Phase 03; SSLCommerz and bKash arrive in Phase 10 (D8), and
the ``LedgerEntry`` that splits each payment between platform and turf comes with them.
The shape is built for that now so Phase 10 adds providers rather than reshaping rows.

A payment points at **either** a booking or (from Phase 08) an order, never both. The
two nullable FKs plus a check constraint are deliberate: a `GenericForeignKey` would buy
nothing here beyond losing referential integrity and join-ability.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
    CANCELLED = "cancelled", _("Cancelled")


class PaymentKind(models.TextChoices):
    """What this payment is *for*, which is not the same as how much it is.

    A booking can be settled in one go, or with an advance now and the balance at the
    turf (DECISIONS D8). The kind is what makes a half-paid booking legible.
    """

    FULL = "full", _("The whole amount")
    ADVANCE = "advance", _("Advance")
    BALANCE = "balance", _("Balance")


class Payment(BaseModel):
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payments",
    )
    order = models.ForeignKey(
        "store.Order",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Cash taken for a store order (Phase 08).",
    )
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
    kind = models.CharField(
        _("kind"), max_length=8, choices=PaymentKind.choices, default=PaymentKind.FULL
    )

    # Phase 10: what the gateway said. `raw_response` is kept because a dispute is
    # settled by what the provider actually sent, not by our reading of it — and it is
    # deliberately the *validated* response, never the redirect the browser carried.
    provider_txn_id = models.CharField(
        _("our transaction id"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text="The id we gave the gateway (`tran_id`). Unique per attempt.",
    )
    bank_txn_id = models.CharField(_("bank transaction id"), max_length=120, blank=True)
    gateway_status = models.CharField(_("gateway status"), max_length=40, blank=True)
    raw_response = models.JSONField(_("validated response"), default=dict, blank=True)
    redirect_url = models.URLField(
        _("gateway URL"), max_length=500, blank=True, help_text="Where the player was sent."
    )
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
            # A payment is for exactly one thing. Without this, a row could be for both
            # a booking and an order, and neither total would be trustworthy.
            models.CheckConstraint(
                condition=(
                    models.Q(booking__isnull=False, order__isnull=True)
                    | models.Q(booking__isnull=True, order__isnull=False)
                ),
                name="payment_has_exactly_one_target",
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

    @property
    def target(self):
        """The booking or the order this is for — exactly one of them (D53)."""
        return self.booking or self.order

    @property
    def refunded_amount(self):
        from decimal import Decimal

        return sum(
            (refund.amount for refund in self.refunds.all() if refund.is_settled),
            Decimal("0"),
        )


class Refund(BaseModel):
    """Money going back (DOMAIN §5).

    A refund is its own row rather than a status on the payment: a partial refund is
    normal — an advance forfeited, a delivery fee returned — and "how much came back"
    has to survive as a number, not as a flag.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        DONE = "done", _("Refunded")
        FAILED = "failed", _("Failed")

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(
        _("amount"), max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    reason = models.CharField(_("reason"), max_length=200)
    status = models.CharField(
        _("status"), max_length=8, choices=Status.choices, default=Status.PENDING
    )
    provider_ref = models.CharField(_("provider reference"), max_length=120, blank=True)
    raw_response = models.JSONField(_("response"), default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_requested",
    )
    settled_at = models.DateTimeField(_("settled at"), null=True, blank=True)

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"৳{self.amount} back ({self.status})"

    @property
    def is_settled(self) -> bool:
        return self.status == self.Status.DONE


class LedgerAccount(models.TextChoices):
    """Who the money belongs to once an event has happened."""

    PLAYER = "player", _("The player")
    PLATFORM = "platform", _("The platform")
    TURF = "turf", _("The turf")
    DELIVERY = "delivery", _("Delivery")


class LedgerEntryType(models.TextChoices):
    BOOKING_FEE = "booking_fee", _("Booking")
    SALE = "sale", _("Sale")
    DELIVERY_FEE = "delivery_fee", _("Delivery fee")
    COMMISSION = "commission", _("Commission")
    REFUND = "refund", _("Refund")
    PAYOUT = "payout", _("Payout")


class LedgerEntry(BaseModel):
    """One side of one movement of money (DOMAIN §12).

    Double-entry in the only sense that matters here: **the entries written for a single
    event sum to zero.** A ৳1000 booking with 10% commission is three lines — the player
    −1000, the turf +900, the platform +100 — and a test adds every event up to prove it.
    Without that, a payout statement is a guess.
    """

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="ledger_entries"
    )
    refund = models.ForeignKey(
        Refund, on_delete=models.PROTECT, null=True, blank=True, related_name="ledger_entries"
    )
    payout = models.ForeignKey(
        "payments.Payout",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    #: Groups the lines of one event, so "does this balance?" is a single query.
    event_id = models.UUIDField(_("event"), db_index=True)

    account = models.CharField(_("account"), max_length=10, choices=LedgerAccount.choices)
    turf = models.ForeignKey(
        "turfs.Turf",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
        help_text="Set when `account` is `turf`.",
    )
    type = models.CharField(_("type"), max_length=14, choices=LedgerEntryType.choices)
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        help_text="Signed: positive is money in, negative is money out.",
    )
    note = models.CharField(_("note"), max_length=200, blank=True)
    occurred_on = models.DateField(_("date"), db_index=True)

    class Meta:
        verbose_name = _("ledger entry")
        verbose_name_plural = _("ledger entries")
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["turf", "-occurred_on"], name="ledger_turf_date_idx"),
            models.Index(fields=["account", "type"], name="ledger_account_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(account=LedgerAccount.TURF, turf__isnull=False)
                    | ~models.Q(account=LedgerAccount.TURF)
                ),
                name="turf_entry_names_a_turf",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_account_display()} {self.amount:+}"


class CommissionPlan(BaseModel):
    """What the platform takes (DOMAIN §12).

    One plan is the default (`turf` null) and a turf may have its own. Percentages are
    stored rather than computed amounts, so a plan change never rewrites history: every
    ledger line keeps the number it was posted with.
    """

    turf = models.OneToOneField(
        "turfs.Turf",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="commission_plan",
        help_text="Null for the platform-wide default.",
    )
    booking_percent = models.DecimalField(
        _("booking commission (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    sales_percent = models.DecimalField(
        _("sales commission (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    monthly_subscription = models.DecimalField(
        _("monthly subscription"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
        help_text="An alternative to commission; zero means commission applies.",
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("commission plan")
        verbose_name_plural = _("commission plans")

    def __str__(self) -> str:
        return f"{self.turf or 'Default'}: {self.booking_percent}% / {self.sales_percent}%"


class Payout(BaseModel):
    """What the platform owes a turf for a period, and whether it has been sent."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SENT = "sent", _("Sent")

    turf = models.ForeignKey("turfs.Turf", on_delete=models.PROTECT, related_name="payouts")
    period_start = models.DateField(_("from"))
    period_end = models.DateField(_("to"))
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    status = models.CharField(
        _("status"), max_length=6, choices=Status.choices, default=Status.DRAFT
    )
    reference = models.CharField(
        _("reference"), max_length=120, blank=True, help_text="Bank or bKash reference."
    )
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_sent",
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("payout")
        verbose_name_plural = _("payouts")
        ordering = ["-period_end"]
        constraints = [
            models.UniqueConstraint(
                fields=["turf", "period_start", "period_end"], name="one_payout_per_period"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.turf}: ৳{self.amount} ({self.period_start} – {self.period_end})"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
PAYMENT_KIND_CHOICES = PaymentKind.choices
REFUND_STATUS_CHOICES = Refund.Status.choices
LEDGER_ACCOUNT_CHOICES = LedgerAccount.choices
LEDGER_ENTRY_TYPE_CHOICES = LedgerEntryType.choices
PAYOUT_STATUS_CHOICES = Payout.Status.choices
