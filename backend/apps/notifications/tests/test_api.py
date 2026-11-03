"""The notification centre endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory()


def make(user, count=1):
    return [
        notify(
            user=user,
            kind=NotificationKind.BOOKING_CREATED,
            url="/bookings/x",
            turf="Arena",
            ground="Pitch",
            when="Fri 18:00",
        )
        for _ in range(count)
    ]


def test_requires_authentication(client):
    assert client.get("/api/v1/me/notifications").status_code == 401


def test_lists_only_my_own(client, user):
    make(user, 2)
    make(UserFactory(), 3)
    client.force_authenticate(user)

    assert len(client.get("/api/v1/me/notifications").data["results"]) == 2


def test_unread_filter(client, user):
    notifications = make(user, 3)
    client.force_authenticate(user)
    client.post("/api/v1/me/notifications/read", {"ids": [str(notifications[0].id)]}, format="json")

    assert len(client.get("/api/v1/me/notifications?unread=true").data["results"]) == 2


def test_unread_count(client, user):
    make(user, 4)
    client.force_authenticate(user)

    assert client.get("/api/v1/me/notifications/unread-count").data["unread"] == 4


def test_mark_all_read(client, user):
    make(user, 3)
    client.force_authenticate(user)

    response = client.post("/api/v1/me/notifications/read", {}, format="json")
    assert response.status_code == 200
    assert response.data["marked"] == 3
    assert client.get("/api/v1/me/notifications/unread-count").data["unread"] == 0


def test_cannot_mark_someone_elses_read(client, user):
    theirs = make(UserFactory(), 1)[0]
    client.force_authenticate(user)

    response = client.post(
        "/api/v1/me/notifications/read", {"ids": [str(theirs.id)]}, format="json"
    )
    assert response.data["marked"] == 0
    theirs.refresh_from_db()
    assert theirs.read_at is None
