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
