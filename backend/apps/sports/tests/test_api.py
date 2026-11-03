"""Catalogue and proposal endpoints, including who may reach them."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import PlatformAdminFactory, UserFactory
from apps.sports.models import Sport, SportProposal

from .factories import SportProposalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def player():
    return UserFactory()


@pytest.fixture
def admin():
    return PlatformAdminFactory()


class TestSportsList:
    def test_requires_authentication(self, client):
        assert client.get("/api/v1/sports").status_code == 401

    def test_returns_the_whole_catalogue_unpaginated(self, client, player):
        client.force_authenticate(player)
        response = client.get("/api/v1/sports")
        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert {s["slug"] for s in response.data} == set(
            Sport.objects.filter(is_active=True).values_list("slug", flat=True)
        )

    def test_each_entry_carries_formats_skills_weights_and_stats(self, client, player):
        client.force_authenticate(player)
        football = next(s for s in client.get("/api/v1/sports").data if s["slug"] == "football")
        assert {f["slug"] for f in football["formats"]} >= {"5v5", "7v7"}
        assert football["formats"][0]["capacity"] == football["formats"][0]["players_per_side"] * 2
        assert {s["key"] for s in football["skills"]} >= {"finishing", "defending"}
        assert {w["attribute"]["key"] for w in football["attribute_weights"]} == {
            "stamina",
            "agility",
            "speed",
            "strength",
        }
        assert {s["key"] for s in football["stat_definitions"]} >= {"goals", "minutes_played"}
        assert football["positions"] == ["GK", "DEF", "MID", "FWD"]

    def test_inactive_sports_are_hidden_from_players(self, client, player):
        Sport.objects.create(name="Kabaddi", slug="kabaddi", is_active=False)
        client.force_authenticate(player)
        slugs = {s["slug"] for s in client.get("/api/v1/sports").data}
        assert "kabaddi" not in slugs

    def test_players_cannot_opt_into_inactive_sports(self, client, player):
        Sport.objects.create(name="Kabaddi", slug="kabaddi", is_active=False)
        client.force_authenticate(player)
        slugs = {s["slug"] for s in client.get("/api/v1/sports?include_inactive=true").data}
        assert "kabaddi" not in slugs

    def test_admins_can_see_sports_awaiting_setup(self, client, admin):
        Sport.objects.create(name="Kabaddi", slug="kabaddi", is_active=False)
        client.force_authenticate(admin)
        slugs = {s["slug"] for s in client.get("/api/v1/sports?include_inactive=true").data}
        assert "kabaddi" in slugs

    def test_retrieve_by_slug(self, client, player):
        client.force_authenticate(player)
        response = client.get("/api/v1/sports/cricket")
        assert response.status_code == 200
        assert response.data["name"] == "Cricket"


def test_attributes_endpoint_lists_them_in_order(client, player):
    client.force_authenticate(player)
    response = client.get("/api/v1/attributes")
    assert response.status_code == 200
    assert [a["key"] for a in response.data] == ["stamina", "agility", "speed", "strength"]


class TestProposals:
    def test_create(self, client, player):
        client.force_authenticate(player)
        response = client.post(
            "/api/v1/sport-proposals", {"name": "Kabaddi", "description": "Sand pit."}
        )
        assert response.status_code == 201
        assert response.data["status"] == "pending"

    def test_create_rejects_an_existing_sport(self, client, player):
        client.force_authenticate(player)
        response = client.post("/api/v1/sport-proposals", {"name": "Football"})
        assert response.status_code == 400
        assert "name" in response.data

    def test_list_shows_only_my_own(self, client, player):
        mine = SportProposalFactory(proposed_by=player)
        SportProposalFactory()
        client.force_authenticate(player)
        response = client.get("/api/v1/sport-proposals")
        assert [p["id"] for p in response.data["results"]] == [str(mine.id)]


class TestAdminProposals:
    def test_queue_is_admin_only(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/admin/sport-proposals").status_code == 403

    def test_queue_lists_everything_and_filters_by_status(self, client, admin):
        pending = SportProposalFactory()
        SportProposalFactory(status=SportProposal.Status.REJECTED)
        client.force_authenticate(admin)
        assert len(client.get("/api/v1/admin/sport-proposals").data["results"]) == 2
        filtered = client.get("/api/v1/admin/sport-proposals?status=pending").data["results"]
        assert [p["id"] for p in filtered] == [str(pending.id)]

    def test_approve_creates_the_sport(self, client, admin):
        proposal = SportProposalFactory(name="Kabaddi")
        client.force_authenticate(admin)
        response = client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/approve", {})
        assert response.status_code == 200
        assert response.data["slug"] == "kabaddi"
        assert Sport.objects.filter(slug="kabaddi").exists()

    def test_approve_is_forbidden_for_players(self, client, player):
        proposal = SportProposalFactory()
        client.force_authenticate(player)
        response = client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/approve", {})
        assert response.status_code == 403

    def test_merge(self, client, admin):
        proposal = SportProposalFactory(name="Soccer")
        football = Sport.objects.get(slug="football")
        client.force_authenticate(admin)
        response = client.post(
            f"/api/v1/admin/sport-proposals/{proposal.id}/merge",
            {"sport_id": str(football.id), "note": "Same game."},
        )
        assert response.status_code == 200
        assert response.data["status"] == "merged"
        assert response.data["merged_into"]["slug"] == "football"

    def test_merge_validates_the_target(self, client, admin):
        proposal = SportProposalFactory()
        client.force_authenticate(admin)
        response = client.post(
            f"/api/v1/admin/sport-proposals/{proposal.id}/merge",
            {"sport_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 400

    def test_reject_requires_a_note(self, client, admin):
        proposal = SportProposalFactory()
        client.force_authenticate(admin)
        assert (
            client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/reject", {}).status_code
            == 400
        )

    def test_reject(self, client, admin):
        proposal = SportProposalFactory()
        client.force_authenticate(admin)
        response = client.post(
            f"/api/v1/admin/sport-proposals/{proposal.id}/reject", {"note": "No court."}
        )
        assert response.status_code == 200
        assert response.data["status"] == "rejected"

    def test_approving_twice_is_a_400_not_a_500(self, client, admin):
        proposal = SportProposalFactory(name="Kabaddi")
        client.force_authenticate(admin)
        client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/approve", {})
        second = client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/approve", {})
        assert second.status_code == 400


def test_an_approved_sport_appears_in_onboarding_once_activated(client, admin, player):
    """Phase 01 acceptance: admin approves a proposal -> it reaches the sport list."""
    proposal = SportProposalFactory(name="Kabaddi")
    client.force_authenticate(admin)
    client.post(f"/api/v1/admin/sport-proposals/{proposal.id}/approve", {})

    sport = Sport.objects.get(slug="kabaddi")
    sport.is_active = True
    sport.save(update_fields=["is_active"])

    client.force_authenticate(player)
    assert "kabaddi" in {s["slug"] for s in client.get("/api/v1/sports").data}
