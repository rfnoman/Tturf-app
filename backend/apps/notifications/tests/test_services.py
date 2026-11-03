"""Notification rendering, delivery and the inbox (DOMAIN §11)."""

from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.services import (
    mark_read,
    notify,
    notify_many,
    render,
    unread_count,
)
from apps.notifications.templates import TEMPLATES

pytestmark = pytest.mark.django_db


def test_every_notification_kind_has_a_template():
    """A missing template would otherwise only surface when that transition first fires."""
    missing = set(NotificationKind.values) - set(TEMPLATES)
    assert missing == set()


def test_no_template_is_defined_for_an_unknown_kind():
    assert set(TEMPLATES) <= set(NotificationKind.values)


class TestRender:
    def test_fills_in_the_context(self):
        title, body, _ = render(
            NotificationKind.BOOKING_CONFIRMED,
            {
                "turf": "Mirpur Turf Club",
                "ground": "Pitch 1",
                "when": "Fri 18:00",
                "price": "৳3200",
            },
        )
        assert "Mirpur Turf Club" in title
        assert "৳3200" in body

    def test_a_missing_placeholder_does_not_raise(self):
        """A notification reading oddly beats a booking transition blowing up."""
        title, body, _ = render(NotificationKind.BOOKING_CONFIRMED, {})
        assert isinstance(title, str)
        assert isinstance(body, str)

    def test_an_unknown_kind_does_not_raise(self):
        title, _, email = render("not_a_kind", {})
        assert title == "not_a_kind"
        assert email is False


class TestNotify:
    def test_creates_a_notification(self):
        user = UserFactory()
        notification = notify(
            user=user,
            kind=NotificationKind.BOOKING_CREATED,
            url="/bookings/abc",
            turf="Arena",
            ground="Pitch",
            when="Fri 18:00",
        )

        assert notification is not None
        assert notification.user == user
        assert notification.url == "/bookings/abc"
        assert notification.is_read is False

    def test_a_missing_user_is_not_an_error(self):
        """A walk-in booked at the counter has no account behind it."""
        assert notify(user=None, kind=NotificationKind.BOOKING_CREATED) is None

    def test_key_events_are_emailed(self, django_capture_on_commit_callbacks):
        """Email goes out through `on_commit`, which no test transaction ever reaches.

        `django_capture_on_commit_callbacks(execute=True)` runs them, which is the only
        way to assert on delivery without committing for real.
        """
        user = UserFactory(email="player@example.com")
        with django_capture_on_commit_callbacks(execute=True):
            notify(
                user=user,
                kind=NotificationKind.BOOKING_CONFIRMED,
                turf="Arena",
                ground="Pitch",
                when="Fri 18:00",
                price="৳2000",
            )
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["player@example.com"]

    def test_delivery_is_timestamped(self, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            notification = notify(
                user=UserFactory(email="player@example.com"),
                kind=NotificationKind.BOOKING_CONFIRMED,
                turf="Arena",
                ground="Pitch",
                when="Fri 18:00",
                price="৳2000",
            )
        notification.refresh_from_db()
        assert notification.emailed_at is not None

    def test_minor_events_are_not_emailed(self, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            notify(
                user=UserFactory(email="player@example.com"),
                kind=NotificationKind.BOOKING_CREATED,
                turf="Arena",
                ground="Pitch",
                when="Fri 18:00",
            )
        assert mail.outbox == []

    def test_an_account_with_no_email_is_not_emailed(self, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            notify(
                user=UserFactory(email=""),
                kind=NotificationKind.BOOKING_CONFIRMED,
                turf="Arena",
                ground="Pitch",
                when="Fri 18:00",
                price="৳2000",
            )
        assert mail.outbox == []

    def test_a_dead_mail_server_does_not_break_the_caller(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        def boom(*args, **kwargs):
            raise OSError("smtp is down")

        monkeypatch.setattr("apps.notifications.services.send_mail", boom)
        with django_capture_on_commit_callbacks(execute=True):
            notification = notify(
                user=UserFactory(email="player@example.com"),
                kind=NotificationKind.BOOKING_CONFIRMED,
                turf="Arena",
                ground="Pitch",
                when="Fri 18:00",
                price="৳2000",
            )

        notification.refresh_from_db()
        # The row survives; only the delivery timestamp is missing.
        assert notification.emailed_at is None


class TestNotifyMany:
    def test_tells_everyone_once(self):
        """The same person can be both owner and manager at a turf."""
        first, second = UserFactory(), UserFactory()
        created = notify_many(
            users=[first, second, first, None],
            kind=NotificationKind.BOOKING_PENDING_CONFIRMATION,
            player="Rafi",
            ground="Pitch",
            when="Fri 18:00",
            expires="17:00",
        )
        assert len(created) == 2
        assert Notification.objects.filter(user=first).count() == 1


class TestInbox:
    def test_unread_count(self):
        user = UserFactory()
        for _ in range(3):
            notify(user=user, kind=NotificationKind.BOOKING_CREATED, turf="A", ground="B", when="C")
        assert unread_count(user=user) == 3

    def test_mark_all_read(self):
        user = UserFactory()
        for _ in range(3):
            notify(user=user, kind=NotificationKind.BOOKING_CREATED, turf="A", ground="B", when="C")

        assert mark_read(user=user) == 3
        assert unread_count(user=user) == 0

    def test_mark_some_read(self):
        user = UserFactory()
        ids = [
            notify(
                user=user, kind=NotificationKind.BOOKING_CREATED, turf="A", ground="B", when="C"
            ).id
            for _ in range(3)
        ]

        assert mark_read(user=user, ids=ids[:1]) == 1
        assert unread_count(user=user) == 2

    def test_marking_read_twice_changes_nothing_the_second_time(self):
        user = UserFactory()
        notify(user=user, kind=NotificationKind.BOOKING_CREATED, turf="A", ground="B", when="C")

        assert mark_read(user=user) == 1
        assert mark_read(user=user) == 0

    def test_one_user_cannot_mark_anothers_read(self):
        mine = UserFactory()
        theirs = UserFactory()
        notify(user=theirs, kind=NotificationKind.BOOKING_CREATED, turf="A", ground="B", when="C")

        assert mark_read(user=mine) == 0
        assert unread_count(user=theirs) == 1
