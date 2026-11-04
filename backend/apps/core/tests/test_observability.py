"""Error reporting sends errors and not secrets (Phase 11 step 5)."""

from __future__ import annotations

from apps.core.observability import _scrub, init_sentry


class TestScrubbing:
    def test_credentials_are_redacted_wherever_they_appear(self):
        # Sentry's own denylist does not know `store_passwd` — that is SSLCommerz's
        # spelling, not a convention anybody would guess (D59).
        event = {
            "request": {"data": {"store_id": "live123", "store_passwd": "hunter2"}},
            "extra": {"nested": [{"card_no": "4111111111111111", "amount": "1000.00"}]},
        }

        cleaned = _scrub(event, None)

        assert cleaned["request"]["data"]["store_passwd"] == "[redacted]"
        assert cleaned["request"]["data"]["store_id"] == "[redacted]"
        assert cleaned["extra"]["nested"][0]["card_no"] == "[redacted]"
        # Everything that is not a credential survives, or the report is useless.
        assert cleaned["extra"]["nested"][0]["amount"] == "1000.00"

    def test_an_ordinary_event_is_untouched(self):
        event = {"message": "Booking confirmed", "extra": {"booking": "abc", "price": 1200}}

        assert _scrub(event, None) == event


class TestInitialisation:
    def test_no_dsn_initialises_nothing(self):
        """Development and CI need no account, and must send nothing (D55's shape)."""
        import sentry_sdk

        init_sentry(dsn="", environment="test", release="", traces_sample_rate=0.0)

        assert sentry_sdk.get_client().dsn is None
