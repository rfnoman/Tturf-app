"""Object-level permissions for turfs (CLAUDE.md).

Roles are permissions on one account (DOMAIN §1), so every check here resolves to "does
this user hold a live ``TurfMembership`` with one of these roles at *this* turf" — which
is what stops staff at turf A from touching turf B.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Ground, Turf, TurfMembership
from .services import TURF_EDIT_ROLES, TURF_STAFF_ROLES, has_turf_role


def _turf_of(obj) -> Turf | None:
    """The turf an object belongs to, for the nested resources."""
    if isinstance(obj, Turf):
        return obj
    turf = getattr(obj, "turf", None)
    if turf is not None:
        return turf
    ground = getattr(obj, "ground", None)
    return ground.turf if isinstance(ground, Ground) else None


class IsTurfOwner(BasePermission):
    """Only the owner may edit the turf, its grounds, hours and prices."""

    message = "You do not own this turf."

    def has_object_permission(self, request, view, obj) -> bool:
        turf = _turf_of(obj)
        return turf is not None and has_turf_role(
            turf=turf, user=request.user, roles=TURF_EDIT_ROLES
        )


class IsTurfStaff(BasePermission):
    """Owner, manager or cashier: anyone who works here.

    Narrow it per view with ``required_roles``, e.g. a view that only managers may POST
    to sets ``required_roles = (TurfMembership.Role.OWNER, TurfMembership.Role.MANAGER)``.
    """

    message = "You are not staff at this turf."

    def has_object_permission(self, request, view, obj) -> bool:
        turf = _turf_of(obj)
        roles = getattr(view, "required_roles", TURF_STAFF_ROLES)
        return turf is not None and has_turf_role(turf=turf, user=request.user, roles=roles)


class IsTurfOwnerOrStaffReadOnly(BasePermission):
    """Owners write; any active staff member reads.

    This is the owner area's rule: the acceptance list requires an invited cashier to
    sign in and *see* the turf without being able to edit it. Read access still depends
    on holding a live membership — the queryset is scoped to the user's own turfs — so
    this is narrower than DRF's stock `IsAuthenticatedOrReadOnly`.
    """

    message = "Only the turf owner can change this."

    def has_object_permission(self, request, view, obj) -> bool:
        turf = _turf_of(obj)
        if turf is None:
            return False
        roles = TURF_STAFF_ROLES if request.method in SAFE_METHODS else TURF_EDIT_ROLES
        return has_turf_role(turf=turf, user=request.user, roles=roles)


class IsTurfStaffOrReadOnly(IsTurfStaff):
    """Staff may write; anyone authenticated may read.

    Used where a resource is public once the turf is approved — a draft turf is still
    hidden, because the queryset, not this class, decides what is visible.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return super().has_object_permission(request, view, obj)


__all__ = [
    "IsTurfOwner",
    "IsTurfOwnerOrStaffReadOnly",
    "IsTurfStaff",
    "IsTurfStaffOrReadOnly",
    "TurfMembership",
]
