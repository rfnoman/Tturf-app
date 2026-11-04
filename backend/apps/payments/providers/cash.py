"""Cash, as a provider.

Phase 03 already records cash at the counter; wrapping it as a provider is what lets the
Phase 10 services stop caring which method they are dealing with.
"""

from __future__ import annotations

from decimal import Decimal

from .base import PaymentProvider, RefundResult, StartedPayment, ValidationResult


class CashProvider(PaymentProvider):
    name = "cash"

    def start(self, *, payment, return_urls: dict) -> StartedPayment:
        """Nothing to start: the player hands over notes at the turf."""
        return StartedPayment(redirect_url="", reference=str(payment.id))

    def validate(self, *, payment, callback: dict) -> ValidationResult:
        """Cash is settled by a staff member pressing a button, not by a callback."""
        return ValidationResult(
            is_paid=payment.status == "paid",
            amount=payment.amount,
            reference=str(payment.id),
            status=payment.status,
        )

    def refund(self, *, payment, amount: Decimal, reason: str) -> RefundResult:
        """Handing cash back is a thing people do, not a thing an API does.

        Accepted, so the ledger and the policy still run — the refund row is then the
        turf's instruction to pay the player out of the till.
        """
        return RefundResult(
            is_accepted=True,
            status="manual",
            reason="Cash refunds are handed over at the turf.",
        )
