from django.apps import AppConfig


class FitnessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fitness"
    label = "fitness"

    def ready(self) -> None:
        """Turn locked matches into activity (DOMAIN §10).

        The same hook Phase 06 uses: `apps.scoring` knows nothing about fitness, and
        this app subscribes rather than being called.
        """
        from apps.scoring.hooks import register_scorecard_locked_hook

        from .hooks import on_scorecard_locked

        register_scorecard_locked_hook(on_scorecard_locked)
