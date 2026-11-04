"""Payment business logic (DOMAIN §5).

Phase 03 only records cash collected at the counter, but the recording is still a
transition with a single writer, so Phase 10's online providers slot in beside it rather
than around it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
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


# ---------------------------------------------------------------------------
# Online payments (Phase 10)
# ---------------------------------------------------------------------------
def advance_percent_for(turf) -> int:
    """How much of a booking has to be paid up front (DECISIONS D8).

    A turf that has not set one takes no advance, which is Phase 03's behaviour. The
    platform default exists for turfs that opt in without choosing a number.
    """
    percent = getattr(turf, "advance_percent", 0) or 0
    return int(percent)


def amount_for(*, booking, kind: str) -> Decimal:
    """What one payment of this kind is worth for a booking."""
    from .models import PaymentKind

    price = Decimal(booking.price)
    if kind == PaymentKind.FULL:
        return price

    advance = (price * Decimal(advance_percent_for(booking.ground.turf)) / Decimal("100")).quantize(
        Decimal("0.01")
    )
    if kind == PaymentKind.ADVANCE:
        return advance
    return price - advance


def _reference(payment) -> str:
    """A transaction id the gateway will accept and we can trace back.

    Short, unique per attempt, and carrying nothing private — an id that encoded a
    player would leak one to anybody who saw a receipt.
    """
    from uuid import uuid4

    return f"TA{uuid4().hex[:18].upper()}"


@transaction.atomic
def start_online_payment(*, target, method: str, kind: str = "full", actor=None) -> Payment:
    """Create a pending payment and ask the provider where to send the player.

    A fresh row per attempt, on purpose: a player who abandons a card page and tries
    again has made two attempts, and a gateway that later validates the first must not
    find it overwritten.
    """
    from django.conf import settings

    from .models import PaymentKind
    from .providers import ProviderError, get_provider

    provider = get_provider(method)
    if not provider.is_configured:
        raise ValidationError({"method": "That payment method is not available right now."})

    is_booking = hasattr(target, "ground")
    if is_booking:
        amount = amount_for(booking=target, kind=kind)
    else:
        amount = Decimal(target.total)
        kind = PaymentKind.FULL

    if amount <= 0:
        raise ValidationError({"amount": "There is nothing to pay."})

    payment = Payment.objects.create(
        booking=target if is_booking else None,
        order=None if is_booking else target,
        method=method,
        kind=kind,
        amount=amount,
        status=PaymentStatus.PENDING,
        provider_txn_id="",
    )
    payment.provider_txn_id = _reference(payment)

    base = settings.PAYMENT_RETURN_BASE_URL.rstrip("/")
    api_base = settings.API_PUBLIC_BASE_URL.rstrip("/")
    try:
        started = provider.start(
            payment=payment,
            return_urls={
                "success": f"{base}/payments/{payment.id}?result=success",
                "fail": f"{base}/payments/{payment.id}?result=failed",
                "cancel": f"{base}/payments/{payment.id}?result=cancelled",
                "ipn": f"{api_base}/api/v1/payments/ipn/{method}",
            },
        )
    except ProviderError as exc:
        # The whole function is atomic, so the pending row rolls back with the raise:
        # an attempt that never reached the gateway leaves nothing behind, which is
        # what a player retrying should find. The log line is the record that matters.
        logger.warning(
            "Could not start a payment",
            extra={"method": method, "reason": str(exc)},
        )
        raise ValidationError({"provider": str(exc)}) from exc

    payment.redirect_url = started.redirect_url
    payment.save()

    logger.info(
        "Payment started",
        extra={"payment": str(payment.id), "method": method, "kind": kind},
    )
    return payment


@transaction.atomic
def settle_payment(*, payment: Payment, callback: dict, actor=None) -> Payment:
    """Decide what really happened, and act on it once.

    Idempotent by design: a gateway that sends the IPN twice — or sends it while the
    player is still on the redirect page — must not confirm a booking twice or post the
    ledger twice. An already-settled payment is returned untouched.
    """
    from .ledger import post_booking_payment, post_order_payment
    from .providers import ProviderError, get_provider

    if payment.status == PaymentStatus.PAID:
        return payment

    provider = get_provider(payment.method)
    try:
        result = provider.validate(payment=payment, callback=callback or {})
    except ProviderError as exc:
        logger.warning(
            "Could not validate a payment",
            extra={"payment": str(payment.id), "reason": str(exc)},
        )
        raise ValidationError({"provider": "Could not reach the payment provider."}) from exc

    payment.gateway_status = result.status[:40]
    payment.raw_response = result.raw
    payment.bank_txn_id = result.bank_reference[:120]

    if not result.is_paid:
        payment.status = PaymentStatus.FAILED
        payment.save()
        logger.info(
            "Payment not valid",
            extra={"payment": str(payment.id), "reason": result.reason},
        )
        return payment

    payment.status = PaymentStatus.PAID
    payment.collected_at = now()
    payment.save()

    if payment.booking_id:
        post_booking_payment(payment=payment)
        _advance_booking(payment=payment, actor=actor)
    else:
        post_order_payment(payment=payment)
        _advance_order(payment=payment, actor=actor)

    logger.info("Payment settled", extra={"payment": str(payment.id)})
    return payment


def _advance_booking(*, payment: Payment, actor=None) -> None:
    """What a paid booking payment means for the booking itself.

    An advance confirms the slot whatever the player's record says: money up front is a
    stronger promise than a reliability score, and it is the reason a turf asks for one
    (DECISIONS D8). Paying in full also marks it paid.
    """
    from apps.bookings.models import BookingStatus
    from apps.bookings.services import confirm_booking, mark_paid

    from .models import PaymentKind

    booking = payment.booking
    booking.refresh_from_db()

    if booking.status == BookingStatus.RESERVED:
        confirm_booking(booking=booking, actor=actor, note="Paid online")
        booking.refresh_from_db()

    if (
        payment.kind in (PaymentKind.FULL, PaymentKind.BALANCE)
        and booking.status == BookingStatus.CONFIRMED
    ):
        mark_paid(booking=booking, actor=actor, record_payment=False)


def _advance_order(*, payment: Payment, actor=None) -> None:
    """A paid order is accepted automatically — the money is already in."""
    from apps.store.models import OrderStatus
    from apps.store.services import accept_order

    order = payment.order
    order.refresh_from_db()
    if order.status == OrderStatus.PLACED:
        accept_order(order=order, actor=actor or order.player)


# ---------------------------------------------------------------------------
# Refunds (DOMAIN §5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RefundPolicy:
    """What a cancellation is worth back, and why."""

    amount: Decimal
    reason: str
    forfeits_advance: bool = False


def refund_due(*, booking, cancelled_by_turf: bool = False, at=None) -> RefundPolicy:
    """How much a cancelled booking gets back (DOMAIN §5).

    The table, in words:

    * **The turf cancelled** — everything back, every time. The player did nothing
      wrong, and a turf that keeps money for its own cancellation will not keep players.
    * **The player cancelled inside the free window** — everything back. That is what
      the window is for.
    * **The player cancelled late** — the advance is forfeited and anything beyond it
      comes back. The advance exists to make a late cancellation cost something
      (DECISIONS D8); refunding it would make it decorative.
    """
    from .models import PaymentKind
    from .models import PaymentStatus as Status

    paid = booking.payments.filter(status=Status.PAID)
    total = sum((payment.amount for payment in paid), Decimal("0"))
    if total <= 0:
        return RefundPolicy(amount=Decimal("0.00"), reason="Nothing was paid.")

    if cancelled_by_turf:
        return RefundPolicy(amount=total, reason="The turf cancelled.")

    moment = at or now()
    free_until = booking.starts_at - timedelta(
        hours=float(booking.ground.turf.cancellation_free_hours)
    )
    if moment <= free_until:
        return RefundPolicy(amount=total, reason="Cancelled inside the free window.")

    advance = sum(
        (payment.amount for payment in paid if payment.kind == PaymentKind.ADVANCE),
        Decimal("0"),
    )
    # With no separate advance the whole payment stands in for one, which is what makes
    # a full prepayment behave like everybody else's deposit.
    forfeited = advance or min(total, amount_for(booking=booking, kind=PaymentKind.ADVANCE))

    return RefundPolicy(
        amount=max(Decimal("0.00"), total - forfeited),
        reason="Cancelled late — the advance is forfeited.",
        forfeits_advance=True,
    )


@transaction.atomic
def refund_booking(*, booking, actor=None, cancelled_by_turf: bool = False) -> list:
    """Give back what the policy says, across however many payments there were."""
    from .ledger import post_refund
    from .models import PaymentStatus as Status
    from .models import Refund
    from .providers import ProviderError, get_provider

    policy = refund_due(booking=booking, cancelled_by_turf=cancelled_by_turf)
    if policy.amount <= 0:
        logger.info("No refund due", extra={"booking": str(booking.id), "reason": policy.reason})
        return []

    remaining = policy.amount
    refunds = []

    # Newest first: the balance comes back before the advance, which is the order a
    # player would expect and keeps a forfeited advance intact.
    for payment in booking.payments.filter(status=Status.PAID).order_by("-created_at"):
        if remaining <= 0:
            break
        already = payment.refunded_amount
        refundable = min(payment.amount - already, remaining)
        if refundable <= 0:
            continue

        refund = Refund.objects.create(
            payment=payment,
            amount=refundable,
            reason=policy.reason,
            requested_by=actor,
        )

        provider = get_provider(payment.method)
        try:
            result = provider.refund(payment=payment, amount=refundable, reason=policy.reason)
        except ProviderError as exc:
            logger.warning(
                "Refund could not be sent",
                extra={"refund": str(refund.id), "reason": str(exc)},
            )
            result = None

        if result is not None and result.is_accepted:
            refund.status = Refund.Status.DONE
            refund.provider_ref = result.reference[:120]
            refund.raw_response = result.raw
            refund.settled_at = now()
        else:
            refund.status = Refund.Status.FAILED
            refund.raw_response = (result.raw if result else {}) or {}

        refund.save()

        if refund.is_settled:
            post_refund(refund=refund)
            if payment.amount - refund.amount <= 0:
                payment.status = Status.REFUNDED
                payment.save(update_fields=["status", "updated_at"])

        refunds.append(refund)
        remaining -= refundable

    return refunds


# ---------------------------------------------------------------------------
# Payouts (DOMAIN §12)
# ---------------------------------------------------------------------------
def payout_statement(*, turf, since, until) -> dict:
    """What a turf earned over a period, and the lines behind it."""
    from .ledger import balance_for
    from .models import LedgerAccount, LedgerEntry

    entries = (
        LedgerEntry.objects.filter(
            account=LedgerAccount.TURF, turf=turf, occurred_on__gte=since, occurred_on__lte=until
        )
        .select_related("payment", "refund")
        .order_by("occurred_on", "created_at")
    )

    by_type: dict[str, Decimal] = {}
    for entry in entries:
        by_type[entry.type] = by_type.get(entry.type, Decimal("0")) + entry.amount

    return {
        "turf": turf,
        "period_start": since,
        "period_end": until,
        "total": balance_for(account=LedgerAccount.TURF, turf=turf, since=since, until=until),
        "by_type": by_type,
        "entries": entries,
        "already_paid": sum(
            (
                payout.amount
                for payout in turf.payouts.filter(
                    period_start__gte=since, period_end__lte=until, status="sent"
                )
            ),
            Decimal("0"),
        ),
    }


@transaction.atomic
def create_payout(*, turf, since, until, actor=None):
    """Draft what the platform owes a turf for a period.

    Drafted rather than sent: money leaving the platform is a person's decision, and
    this only works out the number.
    """
    from .models import Payout

    statement = payout_statement(turf=turf, since=since, until=until)
    amount = statement["total"]
    if amount <= 0:
        raise ValidationError({"amount": "There is nothing to pay out for that period."})

    payout, created = Payout.objects.get_or_create(
        turf=turf,
        period_start=since,
        period_end=until,
        defaults={"amount": amount},
    )
    if not created and payout.status == Payout.Status.DRAFT:
        payout.amount = amount
        payout.save(update_fields=["amount", "updated_at"])

    return payout


@transaction.atomic
def mark_payout_sent(*, payout, actor, reference: str = "", note: str = ""):
    """Record that the transfer actually happened, and post it to the ledger."""
    from .ledger import post_entries
    from .models import LedgerAccount, LedgerEntryType, Payout

    if payout.status == Payout.Status.SENT:
        raise ValidationError({"status": "That payout has already been sent."})

    payout.status = Payout.Status.SENT
    payout.reference = reference[:120]
    payout.note = note[:200]
    payout.sent_at = now()
    payout.sent_by = actor
    payout.save()

    # The turf's balance goes down by what it was paid; the platform's goes up by what
    # it handed over. The two lines are the transfer.
    post_entries(
        payout=payout,
        lines=[
            {
                "account": LedgerAccount.TURF,
                "turf": payout.turf,
                "type": LedgerEntryType.PAYOUT,
                "amount": -payout.amount,
                "note": f"Payout {payout.id}",
            },
            {
                "account": LedgerAccount.PLATFORM,
                "type": LedgerEntryType.PAYOUT,
                "amount": payout.amount,
                "note": f"Payout {payout.id}",
            },
        ],
    )
    return payout
