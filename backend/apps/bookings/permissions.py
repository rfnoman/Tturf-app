"""Who may act on a booking (DOMAIN §1, §5)."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.turfs.services import TURF_STAFF_ROLES, has_turf_role


def is_turf_staff(*, booking, user) -> bool:
    return has_turf_role(turf=booking.turf, user=user, roles=TURF_STAFF_ROLES)


def is_booker(*, booking, user) -> bool:
    return bool(user and user.is_authenticated and booking.booked_by_id == user.id)


class CanViewBooking(BasePermission):
    """The player who booked it, or staff at the turf."""

    message = "This booking is not yours."

    def has_object_permission(self, request, view, obj) -> bool:
        return is_booker(booking=obj, user=request.user) or is_turf_staff(
            booking=obj, user=request.user
        )


class IsBookingTurfStaff(BasePermission):
    """Confirming, taking payment and marking a no-show are the turf's calls, not the player's."""

    message = "Only staff at this turf can do that."

    def has_object_permission(self, request, view, obj) -> bool:
        return is_turf_staff(booking=obj, user=request.user)
