from django.apps import AppConfig


class TurfsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.turfs"
    label = "turfs"

    def ready(self) -> None:
        # Cache invalidation for the public turf page (Phase 11 step 3).
        from . import signals  # noqa: F401
