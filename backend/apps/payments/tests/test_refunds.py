"""The refund policy table and the ledger it writes (DOMAIN §5, §12)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.utils import now
from apps.payments.ledger import balance_for, unbalanced_events
from apps.payments.models import (
    LedgerAccount,
    LedgerEntry,
    PaymentKind,
    PaymentStatus,
    Refund,
)
from apps.payments.providers.base import RefundResult
from apps.payments.services import (
    refund_booking,
    refund_due,
    settle_payment,
    start_online_payment,
)

from .factories import payable_booking

pytestmark = pytest.mark.django_db


def paid_booking(*, kind=PaymentKind.FULL, price="2000.00", advance_percent=25, hours_ahead=48):
    """A booking with money actually through the gateway."""
    booking = payable_booking(advance_percent=advance_percent, price=price)
    if hours_ahead is not None:
        from psycopg.types.range import TimestamptzRange

        from apps.bookings.models import Booking

        start = now() + timedelta(hours=hours_ahead)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(start, start + timedelta(hours=1))
        )
        booking.refresh_from_db()

    payment = start_online_payment(target=booking, method="sslcommerz", kind=kind)
    settle_payment(payment=payment, callback={"val_id": "V1"})
    booking.refresh_from_db()
    return booking


class TestRefundPolicy:
    """The table in DOMAIN §5, cell by cell."""

    def test_the_turf_cancelling_refunds_everything(self):
        booking = paid_booking(hours_ahead=1)  # late, but not the player's doing

        policy = refund_due(booking=booking, cancelled_by_turf=True)

        assert policy.amount == Decimal("2000.00")
        assert policy.forfeits_advance is False

    def test_cancelling_early_refunds_everything(self):
        booking = paid_booking(hours_ahead=48)

        policy = refund_due(booking=booking)

        assert policy.amount == Decimal("2000.00")

    def test_cancelling_late_forfeits_the_advance(self):
        booking = paid_booking(price="2000.00", advance_percent=25, hours_ahead=1)

        policy = refund_due(booking=booking)

        # ৳500 of the ৳2000 stands in for the advance.
        assert policy.amount == Decimal("1500.00")
        assert policy.forfeits_advance is True

    def test_a_late_cancellation_of_an_advance_only_booking_refunds_nothing(self):
        booking = paid_booking(kind=PaymentKind.ADVANCE, hours_ahead=1)

        policy = refund_due(booking=booking)

        assert policy.amount == Decimal("0.00")

    def test_nothing_paid_means_nothing_back(self):
        booking = payable_booking()

        assert refund_due(booking=booking).amount == Decimal("0.00")

    def test_the_boundary_is_the_free_window_itself(self):
        booking = paid_booking(hours_ahead=48)
        free_hours = booking.ground.turf.cancellation_free_hours

        inside = refund_due(booking=booking, at=booking.starts_at - timedelta(hours=free_hours + 1))
        outside = refund_due(
            booking=booking,
            at=booking.starts_at - timedelta(hours=free_hours) + timedelta(minutes=1),
        )

        assert inside.amount == Decimal("2000.00")
        assert outside.forfeits_advance is True


class TestRefunding:
    def test_a_refund_goes_back_through_the_gateway(self):
        booking = paid_booking(hours_ahead=48)

        refunds = refund_booking(booking=booking)

        assert len(refunds) == 1
        assert refunds[0].is_settled
        assert refunds[0].amount == Decimal("2000.00")

    def test_a_fully_refunded_payment_says_so(self):
        booking = paid_booking(hours_ahead=48)

        refund_booking(booking=booking)

        assert booking.payments.get().status == PaymentStatus.REFUNDED

    def test_a_gateway_refusing_leaves_the_refund_failed(self, fake_gateway):
        fake_gateway.refund_answer = RefundResult(is_accepted=False, reason="nope")
        booking = paid_booking(hours_ahead=48)

        refunds = refund_booking(booking=booking)

        assert refunds[0].status == Refund.Status.FAILED
        # Nothing was posted, because nothing moved.
        assert not LedgerEntry.objects.filter(refund=refunds[0]).exists()

    def test_the_balance_comes_back_before_the_advance(self):
        booking = payable_booking(advance_percent=25, price="2000.00")
        for kind in (PaymentKind.ADVANCE, PaymentKind.BALANCE):
            payment = start_online_payment(target=booking, method="sslcommerz", kind=kind)
            settle_payment(payment=payment, callback={"val_id": "V1"})

        from psycopg.types.range import TimestamptzRange

        from apps.bookings.models import Booking

        start = now() + timedelta(hours=1)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(start, start + timedelta(hours=1))
        )
        booking.refresh_from_db()

        refunds = refund_booking(booking=booking)

        # ৳1500 back, all of it from the balance payment; the ৳500 advance is forfeited.
        assert sum(refund.amount for refund in refunds) == Decimal("1500.00")
        assert all(refund.payment.kind == PaymentKind.BALANCE for refund in refunds)

    def test_nothing_due_writes_no_refund(self):
        booking = paid_booking(kind=PaymentKind.ADVANCE, hours_ahead=1)

        assert refund_booking(booking=booking) == []
        assert Refund.objects.count() == 0


class TestLedger:
    def test_a_booking_payment_splits_three_ways(self):
        booking = paid_booking(price="2000.00")
        turf = booking.ground.turf

        assert balance_for(account=LedgerAccount.PLAYER) == Decimal("-2000.00")
        assert balance_for(account=LedgerAccount.TURF, turf=turf) == Decimal("1800.00")
        assert balance_for(account=LedgerAccount.PLATFORM) == Decimal("200.00")

    def test_every_event_balances(self):
        """The invariant the whole ledger rests on."""
        booking = paid_booking(hours_ahead=48)
        refund_booking(booking=booking)

        assert unbalanced_events() == []

    def test_a_refund_unwinds_the_commission_too(self):
        booking = paid_booking(price="2000.00", hours_ahead=48)
        turf = booking.ground.turf

        refund_booking(booking=booking)

        # Everything back to zero: the platform does not keep a cut of a booking that
        # did not happen.
        assert balance_for(account=LedgerAccount.PLAYER) == Decimal("0.00")
        assert balance_for(account=LedgerAccount.TURF, turf=turf) == Decimal("0.00")
        assert balance_for(account=LedgerAccount.PLATFORM) == Decimal("0.00")

    def test_entries_that_do_not_balance_are_refused(self):
        from apps.payments.ledger import post_entries

        with pytest.raises(ValueError, match="do not balance"):
            post_entries(
                lines=[
                    {"account": LedgerAccount.PLATFORM, "type": "commission", "amount": 100},
                ]
            )

    def test_a_turf_on_a_subscription_pays_no_commission(self):
        from apps.payments.ledger import commission_plan_for

        booking = payable_booking(price="2000.00")
        turf = booking.ground.turf
        plan = commission_plan_for(turf)
        plan.turf = turf
        plan.pk = None
        plan.monthly_subscription = Decimal("5000.00")
        plan.save()

        payment = start_online_payment(target=booking, method="sslcommerz", kind=PaymentKind.FULL)
        settle_payment(payment=payment, callback={"val_id": "V1"})

        assert balance_for(account=LedgerAccount.TURF, turf=turf) == Decimal("2000.00")
        assert balance_for(account=LedgerAccount.PLATFORM) == Decimal("0.00")


class TestPayouts:
    def test_a_statement_adds_up_what_a_turf_earned(self):
        from apps.payments.services import payout_statement

        booking = paid_booking(price="2000.00")
        turf = booking.ground.turf
        today = now().date()

        statement = payout_statement(turf=turf, since=today, until=today)

        assert statement["total"] == Decimal("1800.00")
        assert statement["entries"].count() == 1

    def test_marking_a_payout_sent_clears_the_balance(self):
        from apps.payments.services import create_payout, mark_payout_sent

        booking = paid_booking(price="2000.00")
        turf = booking.ground.turf
        today = now().date()

        payout = create_payout(turf=turf, since=today, until=today)
        assert payout.amount == Decimal("1800.00")

        mark_payout_sent(payout=payout, actor=booking.booked_by, reference="BANK-1")

        assert balance_for(account=LedgerAccount.TURF, turf=turf) == Decimal("0.00")
        assert unbalanced_events() == []

    def test_a_payout_cannot_be_sent_twice(self):
        from apps.payments.services import create_payout, mark_payout_sent

        booking = paid_booking(price="2000.00")
        today = now().date()
        payout = create_payout(turf=booking.ground.turf, since=today, until=today)
        mark_payout_sent(payout=payout, actor=booking.booked_by)

        with pytest.raises(Exception, match="already been sent"):
            mark_payout_sent(payout=payout, actor=booking.booked_by)

    def test_nothing_earned_means_no_payout(self):
        from apps.payments.services import create_payout

        booking = payable_booking()
        today = now().date()

        with pytest.raises(Exception, match="nothing to pay out"):
            create_payout(turf=booking.ground.turf, since=today, until=today)
