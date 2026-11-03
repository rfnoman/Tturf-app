"""Profile, onboarding and public-card endpoints."""

from __future__ import annotations

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.players.models import PlayerProfile, PlayerSport
from apps.players.services import add_player_sport, complete_onboarding, get_or_create_profile
from apps.sports.models import Sport

pytestmark = pytest.mark.django_db

CAP = settings.SELF_ASSESSED_RATING_CAP

ONBOARDING = {
    "display_name": "Rafi",
    "area": "Dhanmondi",
    "preferred_side": "right",
    "height_cm": 175,
    "attributes": {"stamina": 65, "agility": 60, "speed": 70, "strength": 55},
    "sports": [
        {"sport": "football", "positions": ["MID"], "skills": {"finishing": 60, "passing": 70}}
    ],
}


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory(first_name="Rafi", last_name="Ahmed")


class TestMyProfile:
    def test_requires_authentication(self, client):
        assert client.get("/api/v1/me/profile").status_code == 401

    def test_creates_the_profile_on_first_access(self, client, user):
        client.force_authenticate(user)
        response = client.get("/api/v1/me/profile")
        assert response.status_code == 200
        assert response.data["onboarding_completed"] is False
        assert response.data["name"] == "Rafi Ahmed"
        assert PlayerProfile.objects.filter(user=user).exists()

    def test_falls_back_to_the_clerk_avatar(self, client, user):
        client.force_authenticate(user)
        assert client.get("/api/v1/me/profile").data["photo_url"] == user.image_url

    def test_patch_updates_fields(self, client, user):
        client.force_authenticate(user)
        response = client.patch("/api/v1/me/profile", {"area": "Banani", "discoverable": False})
        assert response.status_code == 200
        assert response.data["area"] == "Banani"
        assert response.data["discoverable"] is False

    def test_patch_rejects_an_out_of_range_weight(self, client, user):
        client.force_authenticate(user)
        assert client.patch("/api/v1/me/profile", {"weight_kg": "5.0"}).status_code == 400

    def test_patch_can_re_assess_attributes(self, client, user):
        client.force_authenticate(user)
        client.post("/api/v1/me/onboarding", ONBOARDING, format="json")
        response = client.patch(
            "/api/v1/me/profile",
            {"attributes": {"stamina": 70, "agility": 70, "speed": 70, "strength": 70}},
            format="json",
        )
        assert response.status_code == 200
        assert {a["value"] for a in response.data["attributes"]} == {70}

    def test_patch_rejects_an_unknown_attribute(self, client, user):
        client.force_authenticate(user)
        response = client.patch(
            "/api/v1/me/profile", {"attributes": {"telekinesis": 70}}, format="json"
        )
        assert response.status_code == 400

    def test_reliability_and_overall_are_not_writable(self, client, user):
        client.force_authenticate(user)
        client.patch("/api/v1/me/profile", {"reliability_score": 10}, format="json")
        assert (
            PlayerProfile.objects.get(user=user).reliability_score
            == settings.RELIABILITY_STARTING_SCORE
        )


class TestOnboarding:
    def test_completes_and_returns_the_card(self, client, user):
        client.force_authenticate(user)
        response = client.post("/api/v1/me/onboarding", ONBOARDING, format="json")

        assert response.status_code == 200
        assert response.data["onboarding_completed"] is True
        assert len(response.data["sport_cards"]) == 1

        card = response.data["sport_cards"][0]
        assert card["sport"]["slug"] == "football"
        assert card["positions"] == ["MID"]
        assert card["is_provisional"] is True
        assert card["is_verified"] is False
        assert card["overall"] > 0
        assert {s["key"] for s in card["skills"]} == {"finishing", "passing"}

    def test_requires_at_least_one_sport(self, client, user):
        client.force_authenticate(user)
        response = client.post("/api/v1/me/onboarding", {**ONBOARDING, "sports": []}, format="json")
        assert response.status_code == 400
        assert "sports" in response.data

    def test_rejects_the_same_sport_twice(self, client, user):
        client.force_authenticate(user)
        payload = {**ONBOARDING, "sports": [{"sport": "football"}, {"sport": "football"}]}
        assert client.post("/api/v1/me/onboarding", payload, format="json").status_code == 400

    def test_rejects_an_unknown_sport(self, client, user):
        client.force_authenticate(user)
        payload = {**ONBOARDING, "sports": [{"sport": "quidditch"}]}
        assert client.post("/api/v1/me/onboarding", payload, format="json").status_code == 400

    def test_rejects_a_rating_outside_the_scale(self, client, user):
        client.force_authenticate(user)
        payload = {**ONBOARDING, "attributes": {"stamina": 150}}
        assert client.post("/api/v1/me/onboarding", payload, format="json").status_code == 400

    def test_caps_a_claimed_99(self, client, user):
        """Acceptance: a self-assessed card is capped and labelled unverified."""
        client.force_authenticate(user)
        payload = {
            **ONBOARDING,
            "attributes": {"stamina": 99, "agility": 99, "speed": 99, "strength": 99},
            "sports": [{"sport": "football", "skills": {"finishing": 99, "passing": 99}}],
        }
        response = client.post("/api/v1/me/onboarding", payload, format="json")

        assert {a["value"] for a in response.data["attributes"]} == {CAP}
        card = response.data["sport_cards"][0]
        assert card["overall"] == CAP
        assert card["is_provisional"] is True

    def test_attributes_appear_on_the_profile_not_per_sport(self, client, user):
        """DOMAIN §3: shared attributes belong to the player, so they are not per card."""
        client.force_authenticate(user)
        payload = {
            **ONBOARDING,
            "sports": [{"sport": "football"}, {"sport": "badminton"}],
        }
        response = client.post("/api/v1/me/onboarding", payload, format="json")
        assert len(response.data["attributes"]) == 4
        assert len(response.data["sport_cards"]) == 2


class TestMySports:
    def test_add_after_onboarding(self, client, user):
        client.force_authenticate(user)
        client.post("/api/v1/me/onboarding", ONBOARDING, format="json")
        response = client.post(
            "/api/v1/me/sports",
            {"sport": "cricket", "positions": ["Bowler"], "skills": {"bowling": 65}},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["sport"]["slug"] == "cricket"
        assert response.data["positions"] == ["Bowler"]

    def test_add_rejects_an_unknown_sport(self, client, user):
        client.force_authenticate(user)
        assert (
            client.post("/api/v1/me/sports", {"sport": "quidditch"}, format="json").status_code
            == 400
        )

    def test_add_rejects_a_position_the_sport_does_not_have(self, client, user):
        client.force_authenticate(user)
        response = client.post(
            "/api/v1/me/sports", {"sport": "cricket", "positions": ["GK"]}, format="json"
        )
        assert response.status_code == 400

    def test_remove_deletes_a_sport_with_no_history(self, client, user):
        client.force_authenticate(user)
        client.post("/api/v1/me/onboarding", ONBOARDING, format="json")
        response = client.delete("/api/v1/me/sports/football")
        assert response.status_code == 200
        assert response.data["status"] == "removed"
        assert not PlayerSport.objects.filter(profile__user=user).exists()

    def test_remove_only_hides_a_verified_sport(self, client, user):
        client.force_authenticate(user)
        client.post("/api/v1/me/onboarding", ONBOARDING, format="json")
        player_sport = PlayerSport.objects.get(profile__user=user)
        player_sport.is_verified = True
        player_sport.save(update_fields=["is_verified"])

        response = client.delete("/api/v1/me/sports/football")
        assert response.data["status"] == "hidden"
        assert PlayerSport.objects.filter(profile__user=user).exists()

    def test_a_hidden_sport_leaves_the_profile_card(self, client, user):
        client.force_authenticate(user)
        client.post("/api/v1/me/onboarding", ONBOARDING, format="json")
        player_sport = PlayerSport.objects.get(profile__user=user)
        player_sport.is_verified = True
        player_sport.save(update_fields=["is_verified"])
        client.delete("/api/v1/me/sports/football")

        assert client.get("/api/v1/me/profile").data["sport_cards"] == []


class TestPublicPlayerCard:
    def test_another_player_can_open_a_direct_link(self, client, user):
        profile = complete_onboarding(user=user, data={**ONBOARDING, "weight_kg": "72.5"})
        client.force_authenticate(UserFactory())

        response = client.get(f"/api/v1/players/{profile.id}")
        assert response.status_code == 200
        assert response.data["name"] == "Rafi"
        assert len(response.data["sport_cards"]) == 1

    def test_a_direct_link_works_even_when_not_discoverable(self, client, user):
        """DOMAIN §3: `discoverable` gates search, not direct links."""
        profile = complete_onboarding(user=user, data=ONBOARDING)
        profile.discoverable = False
        profile.save(update_fields=["discoverable"])

        client.force_authenticate(UserFactory())
        assert client.get(f"/api/v1/players/{profile.id}").status_code == 200

    def test_hides_private_fields(self, client, user):
        profile = complete_onboarding(
            user=user, data={**ONBOARDING, "date_of_birth": "1998-04-02", "weight_kg": "72.5"}
        )
        client.force_authenticate(UserFactory())
        data = client.get(f"/api/v1/players/{profile.id}").data

        assert "date_of_birth" not in data
        assert "weight_kg" not in data
        assert "discoverable" not in data
        assert data["age"] >= 27

    def test_age_is_null_without_a_birth_date(self, client, user):
        profile = complete_onboarding(user=user, data=ONBOARDING)
        client.force_authenticate(UserFactory())
        assert client.get(f"/api/v1/players/{profile.id}").data["age"] is None

    def test_requires_authentication(self, client, user):
        profile = get_or_create_profile(user)
        assert client.get(f"/api/v1/players/{profile.id}").status_code == 401

    def test_unknown_player_is_a_404(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/players/00000000-0000-0000-0000-000000000000").status_code == 404


def test_card_shows_at_most_six_skills(client, user):
    """DOMAIN §3 asks for six key stats on the card; football defines six skills."""
    client.force_authenticate(user)
    football = Sport.objects.get(slug="football")
    profile = get_or_create_profile(user)
    add_player_sport(
        profile=profile,
        sport=football,
        skills={s.key: 60 for s in football.skills.all()},
    )
    card = client.get("/api/v1/me/profile").data["sport_cards"][0]
    assert len(card["skills"]) <= 6


def test_card_prefers_skills_that_count_toward_the_overall(client, user):
    """With more skills than slots, goalkeeping is the one that drops off."""
    football = Sport.objects.get(slug="football")
    football.skills.create(key="heading", label="Heading", weight="1.000", order=7)
    profile = get_or_create_profile(user)
    add_player_sport(
        profile=profile,
        sport=football,
        skills={s.key: 60 for s in football.skills.all()},
    )

    client.force_authenticate(user)
    keys = {s["key"] for s in client.get("/api/v1/me/profile").data["sport_cards"][0]["skills"]}
    assert "goalkeeping" not in keys
    assert len(keys) == 6
