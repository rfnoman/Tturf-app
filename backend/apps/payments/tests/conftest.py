"""Every payment test runs against a gateway that never touches the network."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fake_gateway(monkeypatch):
    """Swap SSLCommerz for the fake, and reset it between tests.

    Patched in the registry rather than per call site: the services look the provider up
    by name, which is exactly the seam a test should use.
    """
    from apps.payments import providers
    from apps.payments.tests.factories import FakeGateway

    FakeGateway.reset()
    monkeypatch.setitem(providers.PROVIDERS, "sslcommerz", FakeGateway)
    yield FakeGateway
    FakeGateway.reset()
