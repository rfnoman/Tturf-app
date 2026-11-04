"""Error reporting (Phase 11 step 5).

Without this, a booking that fails for one player on one phone is invisible: they shrug,
close the tab, and the first anybody hears of it is "it didn't work" a week later.

Sentry is initialised **only when a DSN is configured**, exactly like web push (D55).
Development and CI need no account and send nothing, and the code path is identical
either way — there is no "if sentry" scattered through the app.

What is deliberately not sent:

- **Request bodies**, via ``send_default_pii=False``. A booking payload carries a phone
  number, a payment callback carries a transaction reference, and an error report is not
  a place to keep either.
- **Anything matching a secret**, via the scrubber below. The default denylist misses
  the names this app actually uses — `store_passwd` is SSLCommerz's spelling, not a
  convention anybody would guess (D59 strips it from stored responses; this stops it
  reaching a third party as well).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Names whose values must never leave the process, on top of Sentry's own defaults.
SENSITIVE = {
    "store_passwd",
    "store_id",
    "card_no",
    "verify_sign",
    "verify_key",
    "clerk_secret_key",
    "vapid_private_key",
    "django_secret_key",
    "password",
    "token",
    "authorization",
}


def _scrub(event, _hint):
    """Drop anything that looks like a credential, wherever it appears in the event."""

    def clean(value):
        if isinstance(value, dict):
            return {
                key: ("[redacted]" if str(key).lower() in SENSITIVE else clean(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(event)


def init_sentry(*, dsn: str, environment: str, release: str, traces_sample_rate: float) -> None:
    """Start reporting. A missing DSN is not an error — it is development."""
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        integrations=[
            DjangoIntegration(),
            # Celery runs the timers that confirm bookings and close votes; a task that
            # dies quietly there is worse than a request that fails loudly.
            CeleryIntegration(),
            # Errors are reported; INFO becomes breadcrumbs, which is the context that
            # makes a report readable without being its own firehose.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=traces_sample_rate,
        # Never. A request body here carries phone numbers and payment references.
        send_default_pii=False,
        before_send=_scrub,
        before_send_transaction=_scrub,
    )
    logger.info("Error reporting enabled", extra={"environment": environment})
