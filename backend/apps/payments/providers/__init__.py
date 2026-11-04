"""Payment providers, chosen by name (DECISIONS D8)."""

from __future__ import annotations

from .base import PaymentProvider, ProviderError, RefundResult, StartedPayment, ValidationResult
from .cash import CashProvider
from .sslcommerz import SSLCommerzProvider

#: Every provider the app knows. bKash joins this map behind the same interface.
PROVIDERS: dict[str, type[PaymentProvider]] = {
    CashProvider.name: CashProvider,
    SSLCommerzProvider.name: SSLCommerzProvider,
}


def get_provider(name: str) -> PaymentProvider:
    """The provider for a payment method."""
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ProviderError(f"No such payment method: {name}.")
    return provider()


__all__ = [
    "PROVIDERS",
    "CashProvider",
    "PaymentProvider",
    "ProviderError",
    "RefundResult",
    "SSLCommerzProvider",
    "StartedPayment",
    "ValidationResult",
    "get_provider",
]
