"""Payment test setup: a booking to pay for, and a gateway that answers on command."""

from __future__ import annotations

from decimal import Decimal

from apps.accounts.tests.factories import UserFactory
from apps.bookings.tests.factories import bookable_ground, next_slot_start
from apps.payments.providers.base import (
    PaymentProvider,
    RefundResult,
    StartedPayment,
    ValidationResult,
)


def payable_booking(*, advance_percent: int = 25, price: str = "2000.00", user=None):
    """An approved turf taking an advance, with one booking on it."""
    from apps.bookings.services import create_booking

    ground, sport_format = bookable_ground()
    turf = ground.turf
    turf.advance_percent = advance_percent
    turf.save(update_fields=["advance_percent"])

    booking = create_booking(
        user=user or UserFactory(),
        ground=ground,
        start=next_slot_start(),
        sport_format=sport_format,
    )
    if price is not None:
        booking.price = Decimal(price)
        booking.save(update_fields=["price"])
    return booking


class FakeGateway(PaymentProvider):
    """A provider that says exactly what a test tells it to.

    Everything about the security of this phase is *what the server does with what the
    gateway says*, so the gateway itself is the one thing worth faking: no network, and
    every answer — valid, wrong amount, somebody else's transaction — is one line.
    """

    name = "sslcommerz"

    #: Set by a test before the code under test runs.
    answer: ValidationResult | None = None
    refund_answer: RefundResult | None = None
    started: list = []
    fail_to_start = False

    def start(self, *, payment, return_urls: dict) -> StartedPayment:
        if FakeGateway.fail_to_start:
            from apps.payments.providers.base import ProviderError

            raise ProviderError("gateway down")

        FakeGateway.started.append({"payment": payment, "urls": return_urls})
        return StartedPayment(
            redirect_url="https://sandbox.example/pay/abc",
            reference=payment.provider_txn_id,
        )

    def validate(self, *, payment, callback: dict) -> ValidationResult:
        if FakeGateway.answer is not None:
            return FakeGateway.answer
        # The default is the honest one: paid, for this payment, for this amount.
        return ValidationResult(
            is_paid=True,
            amount=payment.amount,
            reference=payment.provider_txn_id,
            bank_reference="BANK123",
            status="VALID",
            raw={"status": "VALID"},
        )

    def refund(self, *, payment, amount: Decimal, reason: str) -> RefundResult:
        if FakeGateway.refund_answer is not None:
            return FakeGateway.refund_answer
        return RefundResult(is_accepted=True, reference="REF123", status="success")

    @property
    def is_configured(self) -> bool:
        return True

    @classmethod
    def reset(cls) -> None:
        cls.answer = None
        cls.refund_answer = None
        cls.started = []
        cls.fail_to_start = False
