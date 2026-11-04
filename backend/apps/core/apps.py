from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        # Error reporting, started once per process — web, worker and beat alike, since
        # all three go through `django.setup()`. A missing DSN initialises nothing
        # (Phase 11 step 5).
        from .observability import init_sentry

        init_sentry(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            release=settings.SENTRY_RELEASE,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        )
