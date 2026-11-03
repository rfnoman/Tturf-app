"""Read-side queries for the notification centre."""

from __future__ import annotations

from django.db.models import QuerySet

from .models import Notification


def inbox(user, *, unread_only: bool = False) -> QuerySet[Notification]:
    queryset = Notification.objects.filter(user=user)
    if unread_only:
        queryset = queryset.filter(read_at__isnull=True)
    return queryset
