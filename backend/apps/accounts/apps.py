from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        # Registers the OpenAPI security scheme for ClerkJWTAuthentication.
        from . import schema  # noqa: F401
