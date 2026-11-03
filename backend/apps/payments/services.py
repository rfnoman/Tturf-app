"""Payment business logic (DOMAIN §5).

Phase 03 only records cash collected at the counter, but the recording is still a
transition with a single writer, so Phase 10's online providers slot in beside it rather
than around it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.utils import now

from .models import Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)


@transaction.atomic
def record_cash_payment(*, booking, collected_by, amount: Decimal | None = None) -> Payment:
    """Record cash taken at the turf for a booking.

    Idempotent on purpose: a cashier pressing "mark paid" twice on a slow connection
    must not produce two payment rows, so an existing settled payment is returned as-is.
    """
    settled = booking.payments.filter(status=PaymentStatus.PAID).first()
    if settled is not None:
        return settled

    value = booking.price if amount is None else Decimal(amount)
    if value < 0:
        raise ValidationError({"amount": "A payment cannot be negative."})

    payment, _ = Payment.objects.update_or_create(
        booking=booking,
        method=PaymentMethod.CASH,
        status=PaymentStatus.PENDING,
        defaults={
            "amount": value,
            "status": PaymentStatus.PAID,
            "collected_by": collected_by,
            "collected_at": now(),
        },
    )
    logger.info(
        "Cash payment recorded",
        extra={"booking": str(booking.id), "payment": str(payment.id)},
    )
    return payment


@transaction.atomic
def refund_payment(*, payment: Payment, note: str = "") -> Payment:
    """Mark a settled payment refunded. Cash refunds happen at the counter."""
    if payment.status != PaymentStatus.PAID:
        raise ValidationError({"status": "Only a settled payment can be refunded."})

    payment.status = PaymentStatus.REFUNDED
    payment.note = note or payment.note
    payment.save(update_fields=["status", "note", "updated_at"])
    logger.info("Payment refunded", extra={"payment": str(payment.id)})
    return payment


def amount_paid_for(booking) -> Decimal:
    """Total settled against a booking, for the staff calendar and Phase 10's ledger."""
    return sum(
        (payment.amount for payment in booking.payments.all() if payment.is_settled),
        Decimal("0.00"),
    )
