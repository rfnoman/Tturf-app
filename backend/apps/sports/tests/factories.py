"""Sport catalogue factories.

Note that most tests want the *seeded* catalogue rather than ad-hoc sports: the data
migration runs on the test database, so ``Sport.objects.get(slug="football")`` works
everywhere. These factories exist for the cases that need a sport the catalogue does
not contain.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.sports.models import (
    Attribute,
    Sport,
    SportAttributeWeight,
    SportFormat,
    SportProposal,
    SportSkill,
    StatDefinition,
)


class AttributeFactory(DjangoModelFactory):
    class Meta:
        model = Attribute
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"attribute-{n}")
    label = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())


class SportFactory(DjangoModelFactory):
    class Meta:
        model = Sport
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Test Sport {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    met_value = "6.00"
    positions = factory.List(["ANY"])
    is_active = True


class SportFormatFactory(DjangoModelFactory):
    class Meta:
        model = SportFormat

    sport = factory.SubFactory(SportFactory)
    name = "5v5"
    slug = "5v5"
    players_per_side = 5


class SportSkillFactory(DjangoModelFactory):
    class Meta:
        model = SportSkill

    sport = factory.SubFactory(SportFactory)
    key = factory.Sequence(lambda n: f"skill-{n}")
    label = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())
    weight = "1.000"


class SportAttributeWeightFactory(DjangoModelFactory):
    class Meta:
        model = SportAttributeWeight

    sport = factory.SubFactory(SportFactory)
    attribute = factory.SubFactory(AttributeFactory)
    weight = "1.000"


class StatDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = StatDefinition

    sport = factory.SubFactory(SportFactory)
    key = factory.Sequence(lambda n: f"stat-{n}")
    label = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())


class SportProposalFactory(DjangoModelFactory):
    class Meta:
        model = SportProposal

    proposed_by = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    name = factory.Sequence(lambda n: f"Proposed Sport {n}")
    description = "Popular at our turf."
