"""Rating, discovery and conduct endpoints."""

from __future__ import annotations

from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.core.utils import now
from apps.players.services import add_player_sport, get_or_create_profile
from apps.ratings.models import Availability, ConductReport
from apps.ratings.tasks import rebuild_leaderboards
from apps.scoring.models import TeamSide
from apps.sports.models import Sport

from .factories import locked_match

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def profile_of(teams, side=TeamSide.A, index=0):
    return list(teams[side].players.all())[index].match_player.player.player_profile


class TestPlayerSearch:
    def test_requires_signing_in(self, client):
        assert client.get("/api/v1/players/search").status_code == 401

    def test_returns_players(self, client):
        viewer = UserFactory()
        other = get_or_create_profile(UserFactory())
        other.display_name = "Findable"
        other.save()
        add_player_sport(profile=other, sport=Sport.objects.get(slug="football"))

        client.force_authenticate(viewer)
        response = client.get("/api/v1/players/search", {"sport": "football"})

        assert response.status_code == 200
        names = [row["name"] for row in response.data["results"]]
        assert "Findable" in names

    def test_a_result_carries_no_contact_details(self, client):
        viewer = UserFactory()
        add_player_sport(
            profile=get_or_create_profile(UserFactory()),
            sport=Sport.objects.get(slug="football"),
        )
        client.force_authenticate(viewer)

        row = client.get("/api/v1/players/search", {"sport": "football"}).data["results"][0]
        assert "date_of_birth" not in row
        assert "availability" in row


class TestAvailabilityApi:
    def test_post_and_list_my_windows(self, client):
        user = UserFactory()
        client.force_authenticate(user)

        created = client.post(
            "/api/v1/me/availability",
            {
                "sport": "football",
                "starts_at": (now() + timedelta(hours=2)).isoformat(),
                "ends_at": (now() + timedelta(hours=4)).isoformat(),
                "area": "Mirpur",
                "note": "Free after work",
            },
            format="json",
        )
        assert created.status_code == 201
        assert created.data["sport_slug"] == "football"

        listed = client.get("/api/v1/me/availability")
        assert len(listed.data) == 1

    def test_a_backwards_window_is_rejected(self, client):
        client.force_authenticate(UserFactory())
        response = client.post(
            "/api/v1/me/availability",
            {
                "starts_at": (now() + timedelta(hours=4)).isoformat(),
                "ends_at": (now() + timedelta(hours=2)).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400

    def test_withdrawing_a_window(self, client):
        user = UserFactory()
        window = Availability.objects.create(
            profile=get_or_create_profile(user),
            starts_at=now() + timedelta(hours=2),
            ends_at=now() + timedelta(hours=3),
        )
        client.force_authenticate(user)

        assert client.delete(f"/api/v1/me/availability/{window.id}").status_code == 204
        assert Availability.objects.count() == 0

    def test_one_player_cannot_withdraw_anothers(self, client):
        window = Availability.objects.create(
            profile=get_or_create_profile(UserFactory()),
            starts_at=now() + timedelta(hours=2),
            ends_at=now() + timedelta(hours=3),
        )
        client.force_authenticate(UserFactory())
        assert client.delete(f"/api/v1/me/availability/{window.id}").status_code == 404


class TestTrackRecordApi:
    def test_the_record_lists_grounds(self, client):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        profile = profile_of(teams)
        client.force_authenticate(UserFactory())

        response = client.get(f"/api/v1/players/{profile.id}/track-record")

        assert response.status_code == 200
        assert response.data["grounds"][0]["turf_name"] == match.booking.ground.turf.name
        # The form guide comes with it, so the profile needs one request rather than two.
        assert response.data["totals"]["football"]["form"] == ["win"]

    def test_rating_history_explains_each_change(self, client):
        _match, teams, _ = locked_match(scores=(2, 0))
        profile = profile_of(teams)
        client.force_authenticate(UserFactory())

        response = client.get(f"/api/v1/players/{profile.id}/rating-history", {"sport": "football"})

        assert response.status_code == 200
        assert response.data[0]["delta"] != 0
        assert "components" in response.data[0]["breakdown"]

    def test_fair_play_is_public_to_signed_in_players(self, client):
        _match, teams, _ = locked_match()
        client.force_authenticate(UserFactory())

        response = client.get(f"/api/v1/players/{profile_of(teams).id}/fair-play")

        assert response.status_code == 200
        assert response.data["band"] == "good"


class TestConductApi:
    def test_a_player_reports_another(self, client):
        match, teams, _ = locked_match()
        reporter = teams[TeamSide.A].players.first().match_player.player
        reported = profile_of(teams, TeamSide.B)
        client.force_authenticate(reporter)

        response = client.post(
            f"/api/v1/matches/{match.id}/conduct-reports",
            {"player_id": str(reported.id), "reason": "abusive", "details": "Shouting"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["status"] == "open"

    def test_an_outsider_cannot_report(self, client):
        match, teams, _ = locked_match()
        client.force_authenticate(UserFactory())

        response = client.post(
            f"/api/v1/matches/{match.id}/conduct-reports",
            {"player_id": str(profile_of(teams).id), "reason": "other"},
            format="json",
        )
        # The match is public, so it is visible; reporting it is what is refused.
        assert response.status_code in {400, 404}

    def test_the_queue_is_admin_only(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/admin/conduct-reports").status_code == 403

    def test_an_admin_upholds_a_report(self, client):
        match, teams, _ = locked_match()
        reporter = teams[TeamSide.A].players.first().match_player.player
        reported = profile_of(teams, TeamSide.B)

        client.force_authenticate(reporter)
        report_id = client.post(
            f"/api/v1/matches/{match.id}/conduct-reports",
            {"player_id": str(reported.id), "reason": "unsafe_play"},
            format="json",
        ).data["id"]

        client.force_authenticate(UserFactory(is_platform_admin=True))
        queue = client.get("/api/v1/admin/conduct-reports")
        assert len(queue.data) == 1

        response = client.post(
            f"/api/v1/admin/conduct-reports/{report_id}/review",
            {"uphold": True, "note": "Confirmed by the turf"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["status"] == ConductReport.Status.UPHELD
        assert client.get("/api/v1/admin/conduct-reports").data == []


class TestLeaderboardApi:
    def test_reads_a_turf_board(self, client):
        match, _teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        rebuild_leaderboards()
        client.force_authenticate(UserFactory())

        response = client.get(
            "/api/v1/leaderboard",
            {"sport": "football", "turf": match.booking.ground.turf.slug, "metric": "wins"},
        )

        assert response.status_code == 200
        assert response.data[0]["rank"] == 1
        assert response.data[0]["player_name"]

    def test_an_unknown_metric_is_rejected(self, client):
        client.force_authenticate(UserFactory())
        response = client.get("/api/v1/leaderboard", {"sport": "football", "metric": "vibes"})
        assert response.status_code == 400
