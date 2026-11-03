"""Onboarding, the self-assessment cap and the provisional overall (DOMAIN §3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.players.models import (
    PlayerAttribute,
    PlayerProfile,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
    RatingSource,
)
from apps.players.services import (
    add_player_sport,
    clamp_rating,
    complete_onboarding,
    compute_overall,
    get_or_create_profile,
    refresh_sport_rating,
    remove_player_sport,
    set_player_attributes,
    set_player_skills,
    update_profile,
)
from apps.sports.models import Sport

from .factories import PlayerProfileFactory

pytestmark = pytest.mark.django_db

CAP = settings.SELF_ASSESSED_RATING_CAP


@pytest.fixture
def user():
    return UserFactory(first_name="Rafi", last_name="Ahmed")


@pytest.fixture
def football():
    return Sport.objects.get(slug="football")


@pytest.fixture
def badminton():
    return Sport.objects.get(slug="badminton")


class TestClampRating:
    def test_caps_self_assessed_values(self):
        """Phase 01 rule: an unverified player cannot claim 99."""
        assert clamp_rating(99, source=RatingSource.SELF) == CAP
        assert clamp_rating(CAP + 1, source=RatingSource.SELF) == CAP

    def test_leaves_computed_values_alone(self):
        assert clamp_rating(99, source=RatingSource.COMPUTED) == 99

    def test_clamps_the_floor(self):
        assert clamp_rating(0) == 1
        assert clamp_rating(-50) == 1

    def test_never_exceeds_99_even_when_computed(self):
        assert clamp_rating(500, source=RatingSource.COMPUTED) == 99

    def test_rounds_rather_than_truncating(self):
        assert clamp_rating(49.6) == 50

    def test_rejects_nonsense(self):
        with pytest.raises(ValidationError):
            clamp_rating("quick")


class TestProfileCreation:
    def test_created_on_first_access_with_the_clerk_name(self, user):
        profile = get_or_create_profile(user)
        assert profile.display_name == "Rafi Ahmed"
        assert profile.onboarding_completed is False
        assert profile.reliability_score == settings.RELIABILITY_STARTING_SCORE

    def test_is_idempotent(self, user):
        first = get_or_create_profile(user)
        assert get_or_create_profile(user).pk == first.pk
        assert PlayerProfile.objects.count() == 1

    def test_weight_falls_back_to_the_configured_default(self, user):
        profile = get_or_create_profile(user)
        assert profile.effective_weight_kg == settings.DEFAULT_PLAYER_WEIGHT_KG
        assert profile.weight_is_estimated is True

    def test_a_given_weight_is_not_flagged(self, user):
        profile = get_or_create_profile(user)
        profile.weight_kg = Decimal("72.5")
        assert profile.weight_is_estimated is False


class TestAttributes:
    def test_upserts_and_caps(self, user):
        profile = get_or_create_profile(user)
        set_player_attributes(profile=profile, values={"stamina": 99, "speed": 40})
        assert PlayerAttribute.objects.get(profile=profile, attribute__key="stamina").value == CAP
        assert PlayerAttribute.objects.get(profile=profile, attribute__key="speed").value == 40

    def test_second_call_updates_rather_than_duplicating(self, user):
        profile = get_or_create_profile(user)
        set_player_attributes(profile=profile, values={"stamina": 40})
        set_player_attributes(profile=profile, values={"stamina": 60})
        assert PlayerAttribute.objects.filter(profile=profile).count() == 1
        assert PlayerAttribute.objects.get(profile=profile).value == 60

    def test_rejects_unknown_keys(self, user):
        profile = get_or_create_profile(user)
        with pytest.raises(ValidationError) as exc:
            set_player_attributes(profile=profile, values={"telekinesis": 70})
        assert "telekinesis" in exc.value.message_dict["attributes"][0]


class TestSkills:
    def test_scoped_to_the_sport(self, user, football, badminton):
        profile = get_or_create_profile(user)
        set_player_skills(profile=profile, sport=football, values={"finishing": 70})
        with pytest.raises(ValidationError):
            set_player_skills(profile=profile, sport=badminton, values={"finishing": 70})

    def test_caps_self_assessed_skills(self, user, football):
        profile = get_or_create_profile(user)
        set_player_skills(profile=profile, sport=football, values={"finishing": 99})
        assert PlayerSkill.objects.get(profile=profile).value == CAP


class TestComputeOverall:
    def test_blends_skills_and_attributes(self, user, football):
        profile = get_or_create_profile(user)
        set_player_skills(
            profile=profile,
            sport=football,
            values={
                "finishing": 60,
                "passing": 60,
                "dribbling": 60,
                "defending": 60,
                "positioning": 60,
            },
        )
        set_player_attributes(
            profile=profile,
            values={"stamina": 40, "agility": 40, "speed": 40, "strength": 40},
        )
        # 60 * 0.65 + 40 * 0.35 = 53
        assert compute_overall(profile=profile, sport=football) == 53

    def test_skills_alone_carry_the_whole_weight(self, user, football):
        profile = get_or_create_profile(user)
        set_player_skills(profile=profile, sport=football, values={"finishing": 70})
        assert compute_overall(profile=profile, sport=football) == 70

    def test_attributes_alone_carry_the_whole_weight(self, user, football):
        profile = get_or_create_profile(user)
        set_player_attributes(
            profile=profile,
            values={"stamina": 50, "agility": 50, "speed": 50, "strength": 50},
        )
        assert compute_overall(profile=profile, sport=football) == 50

    def test_goalkeeping_does_not_drag_an_outfielder_down(self, user, football):
        """`counts_toward_overall=False` must be honoured."""
        profile = get_or_create_profile(user)
        set_player_skills(
            profile=profile, sport=football, values={"finishing": 70, "goalkeeping": 1}
        )
        assert compute_overall(profile=profile, sport=football) == 70

    def test_respects_per_sport_attribute_weights(self, user, football, badminton):
        """Strength counts 0.7 in football but 0.5 in badminton, so the overalls differ."""
        profile = get_or_create_profile(user)
        set_player_attributes(
            profile=profile,
            values={"stamina": 70, "agility": 70, "speed": 70, "strength": 20},
        )
        assert compute_overall(profile=profile, sport=football) != compute_overall(
            profile=profile, sport=badminton
        )

    def test_a_player_with_nothing_rated_is_mid_range(self, user, football):
        """Better an obvious "unrated" number than a 1."""
        profile = get_or_create_profile(user)
        assert compute_overall(profile=profile, sport=football) == CAP // 2

    def test_is_deterministic(self, user, football):
        profile = get_or_create_profile(user)
        set_player_skills(profile=profile, sport=football, values={"finishing": 63})
        assert compute_overall(profile=profile, sport=football) == compute_overall(
            profile=profile, sport=football
        )


class TestRefreshSportRating:
    def test_creates_a_provisional_rating(self, user, football):
        profile = get_or_create_profile(user)
        set_player_skills(profile=profile, sport=football, values={"finishing": 60})
        rating = refresh_sport_rating(profile=profile, sport=football)
        assert rating.overall == 60
        assert rating.is_provisional is True

    def test_stops_being_provisional_once_enough_matches_are_counted(self, user, football):
        profile = get_or_create_profile(user)
        rating = refresh_sport_rating(profile=profile, sport=football)
        rating.matches_counted = settings.RATING_PROVISIONAL_MATCHES
        rating.save(update_fields=["matches_counted"])

        assert refresh_sport_rating(profile=profile, sport=football).is_provisional is False

    def test_does_not_duplicate_the_row(self, user, football):
        profile = get_or_create_profile(user)
        refresh_sport_rating(profile=profile, sport=football)
        refresh_sport_rating(profile=profile, sport=football)
        assert PlayerSportRating.objects.filter(profile=profile, sport=football).count() == 1


class TestAddPlayerSport:
    def test_adds_the_sport_with_positions_skills_and_a_rating(self, user, football):
        profile = get_or_create_profile(user)
        player_sport = add_player_sport(
            profile=profile,
            sport=football,
            positions=["MID", "FWD"],
            skills={"finishing": 65, "passing": 70},
        )
        assert player_sport.positions == ["MID", "FWD"]
        assert player_sport.self_assessed == {"finishing": 65, "passing": 70}
        assert PlayerSkill.objects.filter(profile=profile).count() == 2
        assert PlayerSportRating.objects.filter(profile=profile, sport=football).exists()

    def test_starts_unverified(self, user, football):
        profile = get_or_create_profile(user)
        assert add_player_sport(profile=profile, sport=football).is_verified is False

    def test_rejects_positions_the_sport_does_not_have(self, user, football):
        profile = get_or_create_profile(user)
        with pytest.raises(ValidationError) as exc:
            add_player_sport(profile=profile, sport=football, positions=["WICKET KEEPER"])
        assert "positions" in exc.value.message_dict

    def test_rejects_an_inactive_sport(self, user):
        profile = get_or_create_profile(user)
        sport = Sport.objects.create(name="Kabaddi", slug="kabaddi", is_active=False)
        with pytest.raises(ValidationError) as exc:
            add_player_sport(profile=profile, sport=sport)
        assert "sport" in exc.value.message_dict

    def test_adding_twice_updates_rather_than_duplicating(self, user, football):
        profile = get_or_create_profile(user)
        add_player_sport(profile=profile, sport=football, positions=["MID"])
        add_player_sport(profile=profile, sport=football, positions=["FWD"])
        assert PlayerSport.objects.filter(profile=profile, sport=football).count() == 1
        assert PlayerSport.objects.get(profile=profile, sport=football).positions == ["FWD"]

    def test_re_adding_a_hidden_sport_restores_it(self, user, football):
        profile = get_or_create_profile(user)
        player_sport = add_player_sport(profile=profile, sport=football)
        player_sport.is_verified = True
        player_sport.save(update_fields=["is_verified"])
        remove_player_sport(profile=profile, sport=football)

        restored = add_player_sport(profile=profile, sport=football)
        assert restored.is_hidden is False
        assert restored.is_verified is True


class TestRemovePlayerSport:
    def test_a_sport_with_no_history_is_deleted(self, user, football):
        profile = get_or_create_profile(user)
        add_player_sport(profile=profile, sport=football, skills={"finishing": 60})

        assert remove_player_sport(profile=profile, sport=football) is None
        assert not PlayerSport.objects.filter(profile=profile, sport=football).exists()
        assert not PlayerSkill.objects.filter(profile=profile).exists()
        assert not PlayerSportRating.objects.filter(profile=profile, sport=football).exists()

    def test_a_verified_sport_is_only_hidden(self, user, football):
        """History must survive: DOMAIN §3 / phase 01 rules."""
        profile = get_or_create_profile(user)
        player_sport = add_player_sport(profile=profile, sport=football)
        player_sport.is_verified = True
        player_sport.save(update_fields=["is_verified"])

        result = remove_player_sport(profile=profile, sport=football)
        assert result is not None
        assert result.is_hidden is True
        assert PlayerSport.objects.filter(profile=profile, sport=football).exists()

    def test_a_played_sport_is_only_hidden(self, user, football):
        profile = get_or_create_profile(user)
        add_player_sport(profile=profile, sport=football)
        rating = PlayerSportRating.objects.get(profile=profile, sport=football)
        rating.matches_played = 3
        rating.save(update_fields=["matches_played"])

        assert remove_player_sport(profile=profile, sport=football).is_hidden is True

    def test_removing_a_sport_the_player_never_had_is_a_no_op(self, user, football):
        profile = get_or_create_profile(user)
        assert remove_player_sport(profile=profile, sport=football) is None


class TestCompleteOnboarding:
    def payload(self, **overrides):
        data = {
            "display_name": "Rafi",
            "area": "Dhanmondi",
            "preferred_side": "right",
            "height_cm": 175,
            "weight_kg": Decimal("70.0"),
            "attributes": {"stamina": 65, "agility": 60, "speed": 70, "strength": 55},
            "sports": [
                {
                    "sport": "football",
                    "positions": ["MID"],
                    "skills": {"finishing": 60, "passing": 70},
                }
            ],
        }
        data.update(overrides)
        return data

    def test_marks_the_profile_complete(self, user):
        profile = complete_onboarding(user=user, data=self.payload())
        assert profile.onboarding_completed is True
        assert profile.onboarding_completed_at is not None

    def test_writes_profile_fields(self, user):
        profile = complete_onboarding(user=user, data=self.payload())
        assert profile.display_name == "Rafi"
        assert profile.area == "Dhanmondi"
        assert profile.height_cm == 175

    def test_writes_attributes_skills_and_a_rating(self, user):
        profile = complete_onboarding(user=user, data=self.payload())
        assert PlayerAttribute.objects.filter(profile=profile).count() == 4
        assert PlayerSkill.objects.filter(profile=profile).count() == 2
        rating = PlayerSportRating.objects.get(profile=profile, sport__slug="football")
        assert rating.is_provisional is True
        assert rating.overall > 0

    def test_requires_at_least_one_sport(self, user):
        with pytest.raises(ValidationError) as exc:
            complete_onboarding(user=user, data=self.payload(sports=[]))
        assert "sports" in exc.value.message_dict

    def test_rejects_an_unknown_sport(self, user):
        with pytest.raises(ValidationError) as exc:
            complete_onboarding(user=user, data=self.payload(sports=[{"sport": "quidditch"}]))
        assert "quidditch" in exc.value.message_dict["sports"][0]

    def test_rolls_back_entirely_when_a_later_sport_fails(self, user):
        """One bad entry must not leave a half-onboarded profile."""
        payload = self.payload(
            sports=[
                {"sport": "football", "positions": ["MID"]},
                {"sport": "cricket", "positions": ["Goalkeeper"]},
            ]
        )
        with pytest.raises(ValidationError):
            complete_onboarding(user=user, data=payload)

        profile = PlayerProfile.objects.filter(user=user).first()
        assert profile is None or profile.onboarding_completed is False
        assert not PlayerSport.objects.filter(sport__slug="football").exists()

    def test_handles_several_sports(self, user):
        payload = self.payload(
            sports=[
                {"sport": "football", "positions": ["MID"], "skills": {"finishing": 60}},
                {"sport": "badminton", "positions": ["Singles"], "skills": {"smash": 55}},
            ]
        )
        profile = complete_onboarding(user=user, data=payload)
        assert PlayerSport.objects.filter(profile=profile).count() == 2
        assert PlayerSportRating.objects.filter(profile=profile).count() == 2

    def test_falls_back_to_the_clerk_name(self, user):
        profile = complete_onboarding(user=user, data=self.payload(display_name=""))
        assert profile.display_name == "Rafi Ahmed"

    def test_caps_everything_the_player_claimed(self, user):
        payload = self.payload(
            attributes={"stamina": 99},
            sports=[{"sport": "football", "skills": {"finishing": 99}}],
        )
        profile = complete_onboarding(user=user, data=payload)
        assert PlayerAttribute.objects.get(profile=profile).value == CAP
        assert PlayerSkill.objects.get(profile=profile).value == CAP
        assert PlayerSportRating.objects.get(profile=profile).overall <= CAP


class TestUpdateProfile:
    def test_patches_fields(self):
        profile = PlayerProfileFactory()
        update_profile(profile=profile, data={"area": "Banani", "discoverable": False})
        profile.refresh_from_db()
        assert profile.area == "Banani"
        assert profile.discoverable is False

    def test_re_assessing_attributes_recomputes_every_sport_overall(self, football, badminton):
        profile = PlayerProfileFactory()
        add_player_sport(profile=profile, sport=football)
        add_player_sport(profile=profile, sport=badminton)
        before = {r.sport_id: r.overall for r in profile.sport_ratings.all()}

        update_profile(
            profile=profile,
            data={
                "attributes": {"stamina": 70, "agility": 70, "speed": 70, "strength": 70},
            },
        )

        after = {r.sport_id: r.overall for r in PlayerSportRating.objects.filter(profile=profile)}
        assert after != before
        assert set(after.values()) == {70}
