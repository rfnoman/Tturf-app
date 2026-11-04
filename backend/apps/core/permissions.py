from django.conf import settings
from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    """Platform administrators: a Django superuser or ``is_platform_admin``."""

    message = "Platform administrator access required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, "is_platform_admin", False) or user.is_superuser)
        )


class CanReadApiDocs(BasePermission):
    """Who may read the OpenAPI schema and its two documentation UIs.

    Open where ``API_DOCS_PUBLIC`` is set — development, so ``npm run gen:api`` needs no
    credentials — and platform administrators only everywhere else. A complete map of
    every endpoint, its payload and its parameters is the first thing anybody probing
    the API would want, and the people who legitimately need it have accounts.

    Read per request rather than wired into the URL conf at import, so the production
    posture can be tested rather than assumed.
    """

    message = "The API documentation is not public on this deployment."

    def has_permission(self, request, view) -> bool:
        if settings.API_DOCS_PUBLIC:
            return True
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, "is_platform_admin", False) or user.is_superuser)
        )
