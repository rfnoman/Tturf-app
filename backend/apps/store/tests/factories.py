"""Store test setup: a warehouse with stock, a turf with a shelf, and a player."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import Booking
from apps.inventory.models import Product, ProductCategory, ProductKind
from apps.inventory.services import get_or_create_item, location_for_turf, receive_stock, warehouse
from apps.matches.models import MatchPlayer
from apps.matches.services import add_player
from apps.matches.tests.factories import make_match
from apps.store.models import Address, DeliveryZone
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfFactory, TurfMembershipFactory


def platform_product(
    *, name="Whey protein", price="4200.00", on_hand=20, category="supplements", **extra
):
    """Something the platform sells, with stock in the warehouse."""
    product = Product.objects.create(
        owner_type="platform",
        turf=None,
        slug=name.lower().replace(" ", "-"),
        name=name,
        base_price=Decimal(price),
        kind=ProductKind.SALE,
        category=ProductCategory.objects.get(slug=category),
        **extra,
    )
    item = get_or_create_item(location=warehouse(), product=product)
    if on_hand:
        receive_stock(item=item, quantity=on_hand)
        item.refresh_from_db()
    return product, item


def turf_shelf(*, name="Banana", price="15.00", on_hand=20, category="food", **extra):
    """An approved turf with a cashier and something on the shelf."""
    turf = TurfFactory(status="approved")
    cashier = TurfMembershipFactory(
        turf=turf, role=TurfMembership.Role.CASHIER, status=TurfMembership.Status.ACTIVE
    ).user
    product = Product.objects.create(
        owner_type="turf",
        turf=turf,
        slug=name.lower().replace(" ", "-"),
        name=name,
        base_price=Decimal(price),
        kind=ProductKind.SALE,
        category=ProductCategory.objects.get(slug=category),
        **extra,
    )
    item = get_or_create_item(location=location_for_turf(turf), product=product)
    if on_hand:
        receive_stock(item=item, quantity=on_hand)
        item.refresh_from_db()
    return turf, cashier, product, item


def dhaka_zone(*, name="Dhanmondi", fee="60.00", eta=4, **extra) -> DeliveryZone:
    return DeliveryZone.objects.create(
        name=name, areas=[name], fee=Decimal(fee), eta_hours=eta, **extra
    )


def address_for(user, *, area="Dhanmondi", line="Road 27, Dhanmondi") -> Address:
    return Address.objects.create(
        player=user, label="Home", line=line, area=area, phone="+8801700000000"
    )


def match_in(hours: float, *, player=None):
    """A match that kicks off in `hours`, with `player` on the roster."""
    organiser = UserFactory()
    match = make_match(booker=organiser, hours_ahead=max(1, int(hours)))
    if player is not None and player != organiser:
        add_player(match=match, player=player, source=MatchPlayer.Source.INVITE)

    # `make_match` only books on the hour, so the slot is nudged to the exact offset the
    # test asked for — the cutoff tests turn on minutes.
    from psycopg.types.range import TimestamptzRange

    from apps.core.utils import now

    start = now() + timedelta(hours=hours)
    Booking.objects.filter(pk=match.booking_id).update(
        time_range=TimestamptzRange(start, start + timedelta(hours=1))
    )
    match.refresh_from_db()
    return match
