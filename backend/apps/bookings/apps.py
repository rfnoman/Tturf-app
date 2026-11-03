from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"
    label = "bookings"

    def ready(self) -> None:
        """Teach Phase 02's availability selector about bookings (DECISIONS D25).

        Registering here rather than importing from ``apps.turfs`` keeps the dependency
        pointing one way: turfs know nothing about bookings, and the selector written in
        Phase 02 needed no change when they arrived.
        """
        from apps.turfs.availability import register_booked_range_provider

        from .availability import booked_ranges

        register_booked_range_provider(booked_ranges)
