"""Booking factories and the shared "a bookable ground" setup."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import factory
from factory.django import DjangoModelFactory
from psycopg.types.range import TimestamptzRange

from apps.bookings.models import Booking
from apps.core.utils import DHAKA, now
from apps.sports.models import SportFormat
from apps.turfs.tests.factories import GroundFactory, open_all_week, price_everything


def bookable_ground(*, slot_minutes: int = 60, sport: str = "football", fmt: str = "5v5"):
    """An active, fully priced ground at an approved turf, open around the clock.

    Open 00:00–00:00 on purpose: every test can then pick any hour it likes without
    first reasoning about whether the turf happens to be open then.
    """
    ground = GroundFactory(slot_minutes=slot_minutes)
    open_all_week(ground.turf, opens=time(0), closes=time(0))
    sport_format = SportFormat.objects.get(sport__slug=sport, slug=fmt)
    ground.sport_formats.set([sport_format])
    price_everything(ground, price="2000.00")
    return ground, sport_format


def next_slot_start(*, hours_ahead: int = 24, hour: int | None = None) -> datetime:
    """A slot start safely in the future, aligned to the top of a Dhaka hour.

    Alignment matters: availability slices from midnight, so a start of 14:17 would
    never match an offered slot.
    """
    moment = (now() + timedelta(hours=hours_ahead)).astimezone(DHAKA)
    if hour is not None:
        moment = moment.replace(hour=hour)
    return moment.replace(minute=0, second=0, microsecond=0)


class BookingFactory(DjangoModelFactory):
    """Writes a booking row directly — use the services for anything about behaviour."""

    class Meta:
        model = Booking

    ground = factory.SubFactory(GroundFactory)
    booked_by = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    sport = factory.LazyAttribute(lambda o: o.sport_format.sport)
    sport_format = factory.LazyFunction(
        lambda: SportFormat.objects.get(sport__slug="football", slug="5v5")
    )
    time_range = factory.LazyFunction(
        lambda: TimestamptzRange(next_slot_start(), next_slot_start() + timedelta(hours=1))
    )
    price = "2000.00"
