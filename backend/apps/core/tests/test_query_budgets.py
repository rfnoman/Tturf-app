"""Query budgets for the endpoints that get hit most.

An N+1 does not fail a test, raise an error or show up in a code review — it shows up
as a page that is fine with three rows and unusable with thirty. Every endpoint below
builds a nested payload from several tables, so each gets a **budget**: a number of
queries it may not exceed however many rows come back.

The budgets are set from what the code does today, with a little headroom. They are
deliberately not exact — a test that fails when somebody adds a legitimate
``select_related`` teaches people to raise the number without reading it. The assertion
with teeth is the second one in each test: the same request with many more rows must
cost the *same* number of queries.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.matches.tests.factories import make_match
from apps.players.services import complete_onboarding

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def onboard(user, sport: str = "football"):
    return complete_onboarding(
        user=user,
        data={
            "attributes": {"stamina": 60, "agility": 60, "speed": 60, "strength": 60},
            "sports": [{"sport": sport, "positions": [], "skills": {"finishing": 60}}],
        },
    )


@pytest.fixture
def player():
    user = UserFactory()
    onboard(user)
    return user


class TestMatchBoard:
    """The busiest authenticated page: every player opens it to find a game."""

    def test_cost_does_not_grow_with_the_number_of_matches(
        self, client, player, django_assert_max_num_queries
    ):
        client.force_authenticate(player)
        for _ in range(3):
            make_match(booker=UserFactory())

        with django_assert_max_num_queries(8) as captured:
            assert client.get("/api/v1/matches/board").status_code == 200
        small = len(captured.captured_queries)

        for _ in range(12):
            make_match(booker=UserFactory())

        with django_assert_max_num_queries(small):
            response = client.get("/api/v1/matches/board")
        assert len(response.data) >= 15


class TestStoreHome:
    """Opened from the home dashboard and from every match page."""

    def test_has_a_fixed_cost(self, client, player, django_assert_max_num_queries):
        client.force_authenticate(player)
        with django_assert_max_num_queries(10):
            assert client.get("/api/v1/store/home").status_code == 200


class TestTurfDiscovery:
    """The public list, which is the first page most visitors see."""

    def test_cost_does_not_grow_with_the_number_of_turfs(
        self, client, player, django_assert_max_num_queries
    ):
        from apps.turfs.tests.factories import ApprovedTurfFactory

        client.force_authenticate(player)
        ApprovedTurfFactory.create_batch(2)

        with django_assert_max_num_queries(9) as captured:
            assert client.get("/api/v1/turfs").status_code == 200
        small = len(captured.captured_queries)

        ApprovedTurfFactory.create_batch(8)

        with django_assert_max_num_queries(small):
            assert client.get("/api/v1/turfs").status_code == 200


class TestMyBookings:
    def test_has_a_fixed_cost(self, client, player, django_assert_max_num_queries):
        client.force_authenticate(player)
        with django_assert_max_num_queries(8):
            assert client.get("/api/v1/me/bookings").status_code == 200


class TestMatchPage:
    """One match, with its roster and the organiser's decision queues."""

    def test_cost_does_not_grow_with_the_roster(
        self, client, player, django_assert_max_num_queries
    ):
        from apps.accounts.tests.factories import UserFactory as Users
        from apps.matches.services import add_player

        organiser = UserFactory()
        onboard(organiser)
        match = make_match(booker=organiser)
        client.force_authenticate(organiser)

        with django_assert_max_num_queries(14) as captured:
            assert client.get(f"/api/v1/matches/{match.id}").status_code == 200
        empty = len(captured.captured_queries)

        for _ in range(8):
            joiner = Users()
            onboard(joiner)
            add_player(match=match, player=joiner, source="request")

        with django_assert_max_num_queries(empty):
            response = client.get(f"/api/v1/matches/{match.id}")
        assert len(response.data["roster"]) >= 8
