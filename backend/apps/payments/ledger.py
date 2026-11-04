"""The ledger (DOMAIN §12).

Double-entry in the sense that counts: **every event's lines sum to zero.** A ৳1000
booking with 10% commission is three lines — the player −1000, the turf +900, the
platform +100 — and a test adds up every event in the database to prove it stays true.

Amounts are signed: positive is money arriving in that account, negative is money
leaving it. Nothing here calls a gateway or changes a status; it only records what has
already happened.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from apps.core.utils import now, to_dhaka

from .models import (
    CommissionPlan,
    LedgerAccount,
    LedgerEntry,
    LedgerEntryType,
)

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def commission_plan_for(turf) -> CommissionPlan:
    """A turf's plan, or the platform default — created on first use.

    Reading a plan must never fail: a turf with no plan is on the default, and that is a
    normal state rather than a missing row to raise about.
    """
    if turf is not None:
        plan = CommissionPlan.objects.filter(turf=turf, is_active=True).first()
        if plan is not None:
            return plan

    default, _ = CommissionPlan.objects.get_or_create(
        turf=None,
        defaults={
            "booking_percent": Decimal(str(settings.DEFAULT_BOOKING_COMMISSION_PERCENT)),
            "sales_percent": Decimal(str(settings.DEFAULT_SALES_COMMISSION_PERCENT)),
        },
    )
    return default


def commission_on(*, amount: Decimal, turf, kind: str) -> Decimal:
    """What the platform takes from one amount.

    A turf on a subscription pays no commission — that is what the subscription is for —
    so the percentage is skipped entirely rather than set to zero somewhere far away.
    """
    plan = commission_plan_for(turf)
    if plan.monthly_subscription > 0:
        return Decimal("0.00")

    percent = plan.booking_percent if kind == "booking" else plan.sales_percent
    return money(amount * percent / Decimal("100"))


@transaction.atomic
def post_entries(*, lines: list[dict], payment=None, refund=None, payout=None) -> list[LedgerEntry]:
    """Write one event's lines, refusing any set that does not balance.

    The check is the point of the function. A caller that gets the arithmetic wrong
    should find out here, not three months later in a payout statement.
    """
    if not lines:
        return []

    total = sum((money(line["amount"]) for line in lines), Decimal("0"))
    if total != Decimal("0.00"):
        raise ValueError(f"Ledger entries do not balance: {total}")

    event_id = uuid4()
    occurred_on = to_dhaka(now()).date()

    return LedgerEntry.objects.bulk_create(
        [
            LedgerEntry(
                payment=payment,
                refund=refund,
                payout=payout,
                event_id=event_id,
                account=line["account"],
                turf=line.get("turf"),
                type=line["type"],
                amount=money(line["amount"]),
                note=line.get("note", "")[:200],
                occurred_on=occurred_on,
            )
            for line in lines
        ]
    )


def post_booking_payment(*, payment) -> list[LedgerEntry]:
    """A player paid for a booking: the turf earns it, the platform takes its cut."""
    booking = payment.booking
    turf = booking.ground.turf
    amount = money(payment.amount)
    commission = commission_on(amount=amount, turf=turf, kind="booking")
    note = f"Booking {booking.id}"

    return post_entries(
        payment=payment,
        lines=[
            {
                "account": LedgerAccount.PLAYER,
                "type": LedgerEntryType.BOOKING_FEE,
                "amount": -amount,
                "note": note,
            },
            {
                "account": LedgerAccount.TURF,
                "turf": turf,
                "type": LedgerEntryType.BOOKING_FEE,
                "amount": amount - commission,
                "note": note,
            },
            {
                "account": LedgerAccount.PLATFORM,
                "type": LedgerEntryType.COMMISSION,
                "amount": commission,
                "note": note,
            },
        ],
    )


def post_order_payment(*, payment) -> list[LedgerEntry]:
    """A store order was paid for.

    The delivery fee is its own line and never earns commission: it is a cost passed
    through, not revenue to share.
    """
    order = payment.order
    turf = order.location.turf
    goods = money(order.subtotal)
    delivery = money(order.delivery_fee)
    commission = commission_on(amount=goods, turf=turf, kind="sale") if turf else Decimal("0.00")
    note = f"Order {order.id}"

    lines = [
        {
            "account": LedgerAccount.PLAYER,
            "type": LedgerEntryType.SALE,
            "amount": -(goods + delivery),
            "note": note,
        }
    ]

    if turf is not None:
        lines.append(
            {
                "account": LedgerAccount.TURF,
                "turf": turf,
                "type": LedgerEntryType.SALE,
                "amount": goods - commission,
                "note": note,
            }
        )
        if commission:
            lines.append(
                {
                    "account": LedgerAccount.PLATFORM,
                    "type": LedgerEntryType.COMMISSION,
                    "amount": commission,
                    "note": note,
                }
            )
    else:
        # The platform sold its own goods, so it keeps all of it.
        lines.append(
            {
                "account": LedgerAccount.PLATFORM,
                "type": LedgerEntryType.SALE,
                "amount": goods,
                "note": note,
            }
        )

    if delivery:
        lines.append(
            {
                "account": LedgerAccount.DELIVERY,
                "type": LedgerEntryType.DELIVERY_FEE,
                "amount": delivery,
                "note": note,
            }
        )

    return post_entries(payment=payment, lines=lines)


def post_refund(*, refund) -> list[LedgerEntry]:
    """Money going back, unwound in the same proportions it came in.

    The commission is returned too: the platform does not keep a cut of a booking that
    did not happen.
    """
    payment = refund.payment
    amount = money(refund.amount)
    booking = payment.booking
    order = payment.order

    turf = booking.ground.turf if booking else (order.location.turf if order else None)
    kind = "booking" if booking else "sale"
    commission = commission_on(amount=amount, turf=turf, kind=kind) if turf else Decimal("0.00")
    note = f"Refund {refund.id}"

    lines = [
        {
            "account": LedgerAccount.PLAYER,
            "type": LedgerEntryType.REFUND,
            "amount": amount,
            "note": note,
        }
    ]
    if turf is not None:
        lines.append(
            {
                "account": LedgerAccount.TURF,
                "turf": turf,
                "type": LedgerEntryType.REFUND,
                "amount": -(amount - commission),
                "note": note,
            }
        )
        if commission:
            lines.append(
                {
                    "account": LedgerAccount.PLATFORM,
                    "type": LedgerEntryType.REFUND,
                    "amount": -commission,
                    "note": note,
                }
            )
    else:
        lines.append(
            {
                "account": LedgerAccount.PLATFORM,
                "type": LedgerEntryType.REFUND,
                "amount": -amount,
                "note": note,
            }
        )

    return post_entries(refund=refund, lines=lines)


def balance_for(*, account: str, turf=None, since=None, until=None) -> Decimal:
    """What an account has come to over a period."""
    entries = LedgerEntry.objects.filter(account=account)
    if turf is not None:
        entries = entries.filter(turf=turf)
    if since is not None:
        entries = entries.filter(occurred_on__gte=since)
    if until is not None:
        entries = entries.filter(occurred_on__lte=until)

    return money(entries.aggregate(total=Sum("amount"))["total"] or 0)


def unbalanced_events() -> list[dict]:
    """Any event whose lines do not sum to zero — which should always be none.

    Exposed rather than kept in a test: a nightly check that the books balance is worth
    having in production too, and it is the same query either way.
    """
    rows = (
        LedgerEntry.objects.values("event_id")
        .annotate(total=Sum("amount"))
        .exclude(total=Decimal("0.00"))
    )
    return [{"event_id": row["event_id"], "total": row["total"]} for row in rows]
