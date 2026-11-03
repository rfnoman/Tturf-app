"""Player profile factories."""

from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.players.models import (
    PlayerAttribute,
    PlayerProfile,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
)


class PlayerProfileFactory(DjangoModelFactory):
    class Meta:
        model = PlayerProfile
        django_get_or_create = ("user",)

    user = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    display_name = factory.LazyAttribute(lambda o: o.user.full_name)
    area = "Dhanmondi"
    discoverable = True


class OnboardedPlayerFactory(PlayerProfileFactory):
    """A profile past the wizard — but with no sports; add those explicitly."""

    onboarding_completed = True
    onboarding_completed_at = factory.LazyFunction(timezone.now)


class PlayerSportFactory(DjangoModelFactory):
    class Meta:
        model = PlayerSport

    profile = factory.SubFactory(PlayerProfileFactory)
    sport = factory.SubFactory("apps.sports.tests.factories.SportFactory")
    positions = factory.List([])


class PlayerAttributeFactory(DjangoModelFactory):
    class Meta:
        model = PlayerAttribute

    profile = factory.SubFactory(PlayerProfileFactory)
    attribute = factory.SubFactory("apps.sports.tests.factories.AttributeFactory")
    value = 50


class PlayerSkillFactory(DjangoModelFactory):
    class Meta:
        model = PlayerSkill

    profile = factory.SubFactory(PlayerProfileFactory)
    sport_skill = factory.SubFactory("apps.sports.tests.factories.SportSkillFactory")
    value = 50


class PlayerSportRatingFactory(DjangoModelFactory):
    class Meta:
        model = PlayerSportRating

    profile = factory.SubFactory(PlayerProfileFactory)
    sport = factory.SubFactory("apps.sports.tests.factories.SportFactory")
    overall = 50
