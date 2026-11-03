"""Match and squad factories, plus the shared "a match exists" setup."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.bookings.models import BookingMode, BookingVisibility
from apps.bookings.services import create_booking
from apps.bookings.tests.factories import bookable_ground, next_slot_start
from apps.matches.models import Match, Squad, SquadMembership
from apps.matches.services import create_squad


class SquadFactory(DjangoModelFactory):
    class Meta:
        model = Squad
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Test Squad {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    leader = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    accepts_public_requests = False


def make_squad(*, leader, open_squad: bool = False, members=(), name: str | None = None) -> Squad:
    """A squad through the service, so the leader membership exists."""
    squad = create_squad(
        leader=leader,
        name=name or f"Squad of {leader.pk}",
        accepts_public_requests=open_squad,
    )
    for member in members:
        SquadMembership.objects.create(
            squad=squad,
            player=member,
            role=SquadMembership.Role.MEMBER,
            status=SquadMembership.Status.ACTIVE,
        )
    return squad


def make_match(
    *,
    booker,
    visibility: str = BookingVisibility.PUBLIC,
    squad: Squad | None = None,
    hours_ahead: int = 24,
    sport: str = "football",
    fmt: str = "5v5",
    max_players: int | None = None,
) -> Match:
    """A booking and therefore a match, through the real services.

    Going through `create_booking` is deliberate: the match is created by a hook, and a
    test that bypassed it would not be testing the thing the app actually does.
    """
    ground, sport_format = bookable_ground(sport=sport, fmt=fmt)
    if max_players is not None:
        ground.max_players = max_players
        ground.save(update_fields=["max_players"])

    booking = create_booking(
        user=booker,
        ground=ground,
        start=next_slot_start(hours_ahead=hours_ahead),
        sport_format=sport_format,
        mode=BookingMode.GROUP if squad else BookingMode.INDIVIDUAL,
        visibility=visibility,
        squad=squad,
    )
    return Match.objects.select_related("booking", "squad").get(booking=booking)
