from django.apps import AppConfig


class MatchesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.matches"
    label = "matches"

    def ready(self) -> None:
        """Attach to the booking lifecycle (DOMAIN §6).

        Registered as hooks rather than called from ``apps.bookings`` directly: ``Match``
        holds the FK to ``Booking``, so bookings must not import matches. Same pattern as
        Phase 02's availability registry (DECISIONS D25).
        """
        from apps.bookings.hooks import (
            register_booking_created_hook,
            register_booking_transition_hook,
        )

        from .hooks import on_booking_created, on_booking_transitioned

        register_booking_created_hook(on_booking_created)
        register_booking_transition_hook(on_booking_transitioned)
