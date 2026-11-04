"""What the server does with what a gateway says (DOMAIN §5, DECISIONS D8).

This is the security file. A payment callback is attacker-controllable — anyone can POST
to the IPN URL and anyone can type the success URL into a browser — so every test here
asks the same question: **can somebody get a booking confirmed without paying?**
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bookings.models import BookingStatus
from apps.payments.models import LedgerEntry, Payment, PaymentKind, PaymentStatus
from apps.payments.providers.base import ValidationResult
from apps.payments.services import settle_payment, start_online_payment

from .factories import payable_booking

pytestmark = pytest.mark.django_db


def start(booking, *, kind=PaymentKind.ADVANCE) -> Payment:
    return start_online_payment(target=booking, method="sslcommerz", kind=kind)


class TestStarting:
    def test_an_advance_is_a_percentage_of_the_price(self):
        booking = payable_booking(advance_percent=25, price="2000.00")

        payment = start(booking)

        assert payment.amount == Decimal("500.00")
        assert payment.kind == PaymentKind.ADVANCE
        assert payment.status == PaymentStatus.PENDING

    def test_the_player_gets_a_place_to_pay(self):
        payment = start(payable_booking())
        assert payment.redirect_url.startswith("https://")

    def test_every_attempt_gets_its_own_transaction_id(self):
        booking = payable_booking()

        first, second = start(booking), start(booking)

        assert first.provider_txn_id != second.provider_txn_id
        assert Payment.objects.count() == 2

    def test_the_transaction_id_carries_nothing_private(self):
        booking = payable_booking()
        payment = start(booking)

        assert str(booking.booked_by_id) not in payment.provider_txn_id
        assert str(booking.id) not in payment.provider_txn_id

    def test_a_gateway_that_is_down_fails_the_payment_not_the_booking(self, fake_gateway):
        fake_gateway.fail_to_start = True
        booking = payable_booking()

        with pytest.raises(Exception, match="gateway down"):
            start(booking)

        booking.refresh_from_db()
        assert booking.status == BookingStatus.RESERVED
        # The attempt rolls back whole: nothing to clean up, nothing to confuse a retry.
        assert Payment.objects.count() == 0


class TestCallbackSecurity:
    """The whole point of the phase."""

    def test_a_valid_payment_confirms_the_booking(self):
        booking = payable_booking()
        payment = start(booking)

        settle_payment(payment=payment, callback={"val_id": "V1"})

        payment.refresh_from_db()
        booking.refresh_from_db()
        assert payment.status == PaymentStatus.PAID
        assert booking.status == BookingStatus.CONFIRMED

    def test_a_forged_callback_cannot_confirm_anything(self, fake_gateway):
        """The gateway is asked directly, and says it never happened."""
        fake_gateway.answer = ValidationResult(
            is_paid=False, status="FAILED", reason="Gateway said FAILED."
        )
        booking = payable_booking()
        payment = start(booking)

        settle_payment(payment=payment, callback={"val_id": "FORGED"})

        payment.refresh_from_db()
        booking.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert booking.status == BookingStatus.RESERVED

    def test_a_callback_with_the_wrong_amount_is_refused(self, fake_gateway):
        booking = payable_booking(price="2000.00")
        payment = start(booking)
        fake_gateway.answer = ValidationResult(
            is_paid=False,
            amount=Decimal("1.00"),
            reference=payment.provider_txn_id,
            status="VALID",
            reason="The amount does not match.",
        )

        settle_payment(payment=payment, callback={"val_id": "V1"})

        booking.refresh_from_db()
        assert booking.status == BookingStatus.RESERVED

    def test_a_callback_for_somebody_elses_transaction_is_refused(self, fake_gateway):
        booking = payable_booking()
        payment = start(booking)
        fake_gateway.answer = ValidationResult(
            is_paid=False,
            reference="TA-SOMEBODY-ELSE",
            status="VALID",
            reason="That transaction belongs to another payment.",
        )

        settle_payment(payment=payment, callback={"val_id": "V1"})

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    def test_a_duplicate_callback_changes_nothing(self):
        """A gateway may send the IPN twice, or race the redirect."""
        booking = payable_booking()
        payment = start(booking)

        settle_payment(payment=payment, callback={"val_id": "V1"})
        entries_after_first = LedgerEntry.objects.count()
        events_after_first = booking.events.count()

        settle_payment(payment=payment, callback={"val_id": "V1"})

        assert LedgerEntry.objects.count() == entries_after_first
        booking.refresh_from_db()
        assert booking.events.count() == events_after_first

    def test_an_unreachable_gateway_leaves_the_payment_pending(self, fake_gateway, monkeypatch):
        from apps.payments.providers.base import ProviderError

        booking = payable_booking()
        payment = start(booking)

        def boom(*args, **kwargs):
            raise ProviderError("timeout")

        monkeypatch.setattr(fake_gateway, "validate", boom)

        with pytest.raises(Exception, match="Could not reach"):
            settle_payment(payment=payment, callback={"val_id": "V1"})

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING

    def test_nothing_sensitive_is_stored_from_the_gateway(self, fake_gateway):
        """Card data and our own credentials must not reach the database."""
        from apps.payments.providers.sslcommerz import SSLCommerzProvider

        raw = SSLCommerzProvider._safe(
            {
                "status": "VALID",
                "card_no": "432198XXXXXX1234",
                "store_passwd": "hunter2",
                "verify_sign": "abc",
                "amount": "500.00",
            }
        )

        assert raw == {"status": "VALID", "amount": "500.00"}


class TestWhatPaymentMeans:
    def test_an_advance_confirms_even_an_unreliable_player(self):
        """DECISIONS D8: money up front beats a reliability score."""
        booking = payable_booking()
        booking.booked_by.player_profile.reliability_score = 10
        booking.booked_by.player_profile.save(update_fields=["reliability_score"])

        settle_payment(payment=start(booking), callback={"val_id": "V1"})

        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED

    def test_paying_in_full_marks_it_paid(self):
        booking = payable_booking()

        settle_payment(payment=start(booking, kind=PaymentKind.FULL), callback={"val_id": "V1"})

        booking.refresh_from_db()
        assert booking.status == BookingStatus.PAID

    def test_an_online_payment_does_not_also_record_cash(self):
        booking = payable_booking()
        settle_payment(payment=start(booking, kind=PaymentKind.FULL), callback={"val_id": "V1"})

        assert booking.payments.count() == 1
        assert booking.payments.get().method == "sslcommerz"

    def test_the_balance_is_the_rest_of_the_price(self):
        booking = payable_booking(advance_percent=25, price="2000.00")
        settle_payment(payment=start(booking), callback={"val_id": "V1"})

        balance = start(booking, kind=PaymentKind.BALANCE)

        assert balance.amount == Decimal("1500.00")

    def test_a_turf_taking_no_advance_asks_for_the_whole_price(self):
        booking = payable_booking(advance_percent=0, price="2000.00")

        assert start(booking, kind=PaymentKind.FULL).amount == Decimal("2000.00")
