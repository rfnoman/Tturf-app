"""Turf factories."""

from __future__ import annotations

from datetime import time

import factory
from django.contrib.gis.geos import Point
from factory.django import DjangoModelFactory

from apps.turfs.models import (
    Amenity,
    Closure,
    Ground,
    OperatingHours,
    PriceRule,
    Turf,
    TurfMembership,
)

#: Dhanmondi, Dhaka — the default centre for geo tests.
DHANMONDI = (90.3760, 23.7465)


class AmenityFactory(DjangoModelFactory):
    class Meta:
        model = Amenity
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"amenity-{n}")
    label = factory.LazyAttribute(lambda o: o.key.replace("-", " ").title())


class TurfFactory(DjangoModelFactory):
    class Meta:
        model = Turf
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Test Turf {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    address = "Road 27, Dhanmondi, Dhaka"
    area = "Dhanmondi"
    city = "Dhaka"
    location = factory.LazyFunction(lambda: Point(*DHANMONDI, srid=4326))
    status = Turf.Status.DRAFT


class ApprovedTurfFactory(TurfFactory):
    status = Turf.Status.APPROVED


class GroundFactory(DjangoModelFactory):
    class Meta:
        model = Ground

    turf = factory.SubFactory(ApprovedTurfFactory)
    name = factory.Sequence(lambda n: f"Pitch {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    max_players = 10
    slot_minutes = 60
    is_active = True


class OperatingHoursFactory(DjangoModelFactory):
    class Meta:
        model = OperatingHours

    turf = factory.SubFactory(ApprovedTurfFactory)
    weekday = 0
    open_time = time(8, 0)
    close_time = time(22, 0)


class PriceRuleFactory(DjangoModelFactory):
    class Meta:
        model = PriceRule

    ground = factory.SubFactory(GroundFactory)
    weekdays = factory.List([])
    start_time = time(0, 0)
    end_time = time(0, 0)  # a full day: start == end reads as crossing midnight
    price = "1500.00"
    label = "Standard"


class ClosureFactory(DjangoModelFactory):
    class Meta:
        model = Closure

    turf = factory.SubFactory(ApprovedTurfFactory)
    reason = "Maintenance"


class TurfMembershipFactory(DjangoModelFactory):
    class Meta:
        model = TurfMembership

    turf = factory.SubFactory(ApprovedTurfFactory)
    user = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    role = TurfMembership.Role.OWNER
    status = TurfMembership.Status.ACTIVE


def open_all_week(turf: Turf, opens=time(8, 0), closes=time(22, 0)) -> None:
    """Give a turf the same hours every day — the usual test setup."""
    for weekday in range(7):
        OperatingHoursFactory(turf=turf, weekday=weekday, open_time=opens, close_time=closes)


def price_everything(ground: Ground, price: str = "1500.00") -> PriceRule:
    """One rule covering the whole week, so the ground can be activated."""
    return PriceRuleFactory(
        ground=ground, weekdays=[], start_time=time(0, 0), end_time=time(0, 0), price=price
    )
