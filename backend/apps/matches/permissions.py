"""Who may open and act on a match (DOMAIN §6)."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from .services import can_view_match, is_organiser


class CanViewMatch(BasePermission):
    """On the roster, the organiser, on the board, in the squad, or invited."""

    message = "You cannot see this match."

    def has_object_permission(self, request, view, obj) -> bool:
        return can_view_match(match=obj, user=request.user)


class IsMatchOrganiser(BasePermission):
    """Approving requests, deciding proposals and removing players."""

    message = "Only the organiser can do that."

    def has_object_permission(self, request, view, obj) -> bool:
        return is_organiser(match=obj, user=request.user)
