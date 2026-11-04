"""Fitness endpoints: the dashboard, activity, goals, bundles, reminders and push."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.fitness.models import ActivityLog, ActivitySource, Bundle, BundleItem, PushSubscription

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def log_for(user, *, days_ago=0, minutes=60, source=ActivitySource.MATCH):
    from apps.core.utils import now, to_dhaka

    return ActivityLog.objects.create(
        player=user,
        happened_on=to_dhaka(now()).date() - timedelta(days=days_ago),
        minutes=minutes,
        est_calories=minutes * 7,
        source=source,
    )


class TestDashboard:
    def test_it_needs_signing_in(self, client):
        assert client.get("/api/v1/me/dashboard").status_code == 401

    def test_a_new_player_gets_an_empty_week_not_an_error(self, client):
        client.force_authenticate(UserFactory())

        response = client.get("/api/v1/me/dashboard")

        assert response.status_code == 200
        assert response.data["week"]["minutes"] == 0
        assert response.data["streak"]["current"] == 0
        assert response.data["goals"] == []

    def test_it_shows_this_week(self, client):
        user = UserFactory()
        log_for(user, minutes=75)
        client.force_authenticate(user)

        data = client.get("/api/v1/me/dashboard").data

        assert data["week"]["minutes"] == 75
        assert data["week"]["sessions"] == 1
        assert len(data["recent"]) == 1


class TestActivityApi:
    def test_adding_a_gym_session(self, client):
        user = UserFactory()
        client.force_authenticate(user)

        response = client.post("/api/v1/me/activity", {"minutes": 45, "note": "Gym"}, format="json")

        assert response.status_code == 201
        assert response.data["source"] == ActivitySource.MANUAL
        assert response.data["est_calories"] > 0

    def test_a_session_in_the_future_is_refused(self, client):
        client.force_authenticate(UserFactory())

        response = client.post(
            "/api/v1/me/activity",
            {"minutes": 30, "happened_on": (date.today() + timedelta(days=1)).isoformat()},
            format="json",
        )
        assert response.status_code == 400

    def test_a_sport_can_be_named(self, client):
        client.force_authenticate(UserFactory())

        response = client.post(
            "/api/v1/me/activity", {"minutes": 60, "sport": "football"}, format="json"
        )

        assert response.status_code == 201
        assert response.data["sport_name"] == "Football"

    def test_the_history_is_mine_alone(self, client):
        mine, theirs = UserFactory(), UserFactory()
        log_for(mine)
        log_for(theirs)
        client.force_authenticate(mine)

        assert len(client.get("/api/v1/me/activity").data) == 1

    def test_the_window_can_be_narrowed(self, client):
        user = UserFactory()
        log_for(user, days_ago=200)
        log_for(user, days_ago=2)
        client.force_authenticate(user)

        assert len(client.get("/api/v1/me/activity", {"days": 7}).data) == 1

    def test_one_weeks_totals(self, client):
        user = UserFactory()
        log_for(user, minutes=30)
        client.force_authenticate(user)

        response = client.get("/api/v1/me/activity/week")

        assert response.status_code == 200
        assert response.data["minutes"] == 30
        assert response.data["week_start"] <= response.data["week_end"]

    def test_a_malformed_date_is_rejected(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/me/activity/week", {"date": "last tuesday"}).status_code == 400


class TestGoalsApi:
    def test_setting_and_reading_a_goal(self, client):
        user = UserFactory()
        client.force_authenticate(user)

        created = client.post(
            "/api/v1/me/goals", {"type": "minutes_per_week", "target": 180}, format="json"
        )

        assert created.status_code == 200
        assert created.data[0]["target"] == 180
        assert client.get("/api/v1/me/goals").data[0]["percent"] == 0

    def test_progress_moves_with_activity(self, client):
        user = UserFactory()
        client.force_authenticate(user)
        client.post("/api/v1/me/goals", {"type": "minutes_per_week", "target": 120}, format="json")
        log_for(user, minutes=60)

        assert client.get("/api/v1/me/goals").data[0]["percent"] == 50

    def test_zero_retires_a_goal(self, client):
        user = UserFactory()
        client.force_authenticate(user)
        client.post("/api/v1/me/goals", {"type": "matches_per_week", "target": 3}, format="json")

        response = client.post(
            "/api/v1/me/goals", {"type": "matches_per_week", "target": 0}, format="json"
        )

        assert response.data == []


class TestBundlesApi:
    def make_bundle(self, *, products=(), slug="kit"):
        bundle = Bundle.objects.create(name="Evening football kit", slug=slug)
        for product, quantity in products:
            BundleItem.objects.create(bundle=bundle, product=product, quantity=quantity)
        return bundle

    def test_bundles_are_listed(self, client):
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water")
        self.make_bundle(products=[(water, 2)])
        client.force_authenticate(UserFactory())

        rows = client.get("/api/v1/bundles").data

        assert rows[0]["name"] == "Evening football kit"
        assert rows[0]["items"][0]["quantity"] == 2

    def test_one_tap_fills_the_cart(self, client):
        """The acceptance line: the whole kit in one tap."""
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", on_hand=10)
        bar, _bar = platform_product(name="Protein bar", on_hand=10)
        self.make_bundle(products=[(water, 2), (bar, 1)], slug="kit")
        user = UserFactory()
        client.force_authenticate(user)

        response = client.post("/api/v1/bundles/kit/add", {}, format="json")

        assert response.status_code == 200
        assert len(response.data["added"]) == 2
        assert client.get("/api/v1/store/cart").data["item_count"] == 3

    def test_an_empty_shelf_is_explained(self, client):
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", on_hand=0)
        self.make_bundle(products=[(water, 1)], slug="kit")
        client.force_authenticate(UserFactory())

        response = client.post("/api/v1/bundles/kit/add", {}, format="json")

        assert response.status_code == 400
        assert "stock" in str(response.data)


class TestRemindersApi:
    def test_defaults_appear_on_first_read(self, client):
        client.force_authenticate(UserFactory())

        response = client.get("/api/v1/me/reminders")

        assert response.status_code == 200
        assert response.data["hydration"] is True
        assert response.data["push_enabled"] is False

    def test_switching_one_off(self, client):
        client.force_authenticate(UserFactory())

        response = client.patch("/api/v1/me/reminders", {"hydration": False}, format="json")

        assert response.data["hydration"] is False
        assert response.data["recovery"] is True

    def test_quiet_hours_can_be_set(self, client):
        client.force_authenticate(UserFactory())

        response = client.patch(
            "/api/v1/me/reminders",
            {"quiet_from": "23:00", "quiet_until": "06:30"},
            format="json",
        )

        assert response.data["quiet_from"] == "23:00:00"


class TestPushApi:
    SUBSCRIPTION = {
        "endpoint": "https://push.example.com/abc123",
        "p256dh": "BPublicKeyBytes",
        "auth": "AuthSecret",
        "user_agent": "Chrome on Android",
    }

    def test_registering_a_browser_turns_push_on(self, client):
        user = UserFactory()
        client.force_authenticate(user)

        response = client.post("/api/v1/me/push", self.SUBSCRIPTION, format="json")

        assert response.status_code == 201
        assert PushSubscription.objects.filter(player=user).count() == 1
        assert client.get("/api/v1/me/reminders").data["push_enabled"] is True

    def test_registering_twice_is_one_browser(self, client):
        client.force_authenticate(UserFactory())
        client.post("/api/v1/me/push", self.SUBSCRIPTION, format="json")
        client.post("/api/v1/me/push", self.SUBSCRIPTION, format="json")

        assert PushSubscription.objects.count() == 1

    def test_a_browser_can_be_forgotten(self, client):
        user = UserFactory()
        client.force_authenticate(user)
        client.post("/api/v1/me/push", self.SUBSCRIPTION, format="json")

        response = client.delete(f"/api/v1/me/push?endpoint={self.SUBSCRIPTION['endpoint']}")

        assert response.status_code == 204
        assert PushSubscription.objects.count() == 0


def test_push_is_skipped_when_there_are_no_keys(settings):
    """Development and CI have no VAPID keys, and that must not be an error."""
    from apps.notifications.models import NotificationKind
    from apps.notifications.push import send_push
    from apps.notifications.services import notify

    settings.VAPID_PRIVATE_KEY = ""
    user = UserFactory()
    notification = notify(user=user, kind=NotificationKind.MATCH_DAY, sport="Football")

    assert send_push(notification=notification) == 0
