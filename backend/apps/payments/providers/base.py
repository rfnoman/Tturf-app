"""The payment provider interface (DECISIONS D8).

Every provider answers the same four questions — how do I start a payment, what did the
gateway really say, can I give the money back, and what is this provider called — so the
services above never branch on "is this cash or a card".

The one rule that matters here: **the browser's redirect is a hint, never evidence.** A
player can forge the success URL; only a server-to-server validation call decides whether
money moved. Every implementation of `validate` therefore talks to the provider, and
nothing in this package trusts its own callback payload.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class StartedPayment:
    """What a provider needs the player to do next."""

    #: Where to send the player. Empty for cash, which needs no round trip.
    redirect_url: str = ""
    #: The id we gave the provider for this attempt.
    reference: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    """What the provider says actually happened, once asked directly."""

    is_paid: bool
    amount: Decimal | None = None
    currency: str = "BDT"
    #: Our own transaction id, echoed back.
    reference: str = ""
    bank_reference: str = ""
    status: str = ""
    raw: dict = field(default_factory=dict)
    #: Why not, when `is_paid` is False — for the log, never for the player.
    reason: str = ""


@dataclass(frozen=True)
class RefundResult:
    is_accepted: bool
    reference: str = ""
    status: str = ""
    raw: dict = field(default_factory=dict)
    reason: str = ""


class PaymentProvider(ABC):
    """One way of taking money."""

    #: Matches `PaymentMethod`.
    name: str = ""

    @abstractmethod
    def start(self, *, payment, return_urls: dict) -> StartedPayment:
        """Begin a payment and say where to send the player."""

    @abstractmethod
    def validate(self, *, payment, callback: dict) -> ValidationResult:
        """Ask the provider what really happened. Never trust `callback` alone."""

    def refund(self, *, payment, amount: Decimal, reason: str) -> RefundResult:
        """Give money back. Providers that cannot say so."""
        return RefundResult(is_accepted=False, reason=f"{self.name} cannot refund automatically.")

    @property
    def is_configured(self) -> bool:
        """Can this provider actually be used right now?"""
        return True


class ProviderError(Exception):
    """The provider could not be reached or answered nonsense.

    Deliberately not a `ValidationError`: nothing is wrong with what the player did, and
    the difference decides whether the UI says "try again" or "fix this".
    """
