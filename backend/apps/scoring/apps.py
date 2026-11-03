from django.apps import AppConfig


class ScoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scoring"
    label = "scoring"

    def ready(self) -> None:
        """Register the per-sport scorecard validators (DOMAIN §7)."""
        from . import validators  # noqa: F401
