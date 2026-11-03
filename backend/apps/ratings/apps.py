from django.apps import AppConfig


class RatingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ratings"
    label = "ratings"

    def ready(self) -> None:
        """Subscribe to Phase 05's `scorecard_locked` hook (DOMAIN §8).

        The engine reads scorecards, so `apps.scoring` must not import this app; it
        fires the hook and this registers for it. Same pattern as D25 and D35.
        """
        from apps.scoring.hooks import register_scorecard_locked_hook

        from .hooks import on_scorecard_locked

        register_scorecard_locked_hook(on_scorecard_locked)
