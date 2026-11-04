"""Read-side queries for the store (CLAUDE.md)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Prefetch, Q, QuerySet

from apps.core.utils import now
from apps.inventory.models import StockItem, StockLocation
from apps.inventory.services import warehouse

from .models import SETTLED_STATUSES, Order, OrderStatus


def shoppable_stock(
    *,
    location: StockLocation,
    category: str | None = None,
    tag: str | None = None,
    sport: str | None = None,
    max_calories: int | None = None,
    min_protein: int | None = None,
    query: str | None = None,
) -> QuerySet[StockItem]:
    """What is actually buyable at one source, with the fitness filters (DOMAIN §9).

    Filtering on the *stock*, not the product: a product with nothing behind it is a
    disappointment waiting to happen, and price belongs to the location.
    """
    items = (
        StockItem.objects.filter(
            location=location,
            product__is_active=True,
            product__kind="sale",
            on_hand__gt=0,
        )
        .select_related("product", "product__category", "location", "location__turf")
        .prefetch_related("product__sports")
    )

    if category:
        items = items.filter(product__category__slug=category)
    if tag:
        items = items.filter(product__tags__contains=[tag])
    if sport:
        items = items.filter(product__sports__slug=sport)
    if max_calories is not None:
        items = items.filter(
            Q(product__calories__lte=max_calories) | Q(product__calories__isnull=True)
        )
    if min_protein is not None:
        items = items.filter(product__protein_g__gte=min_protein)
    if query:
        items = items.filter(product__name__icontains=query)

    return items.distinct().order_by("product__category__order", "product__name")


def next_match_for(user, *, within_days: int = 7):
    """The player's next match, which is what the store leads with (DOMAIN §9)."""
    from apps.matches.models import Match, MatchStatus

    return (
        Match.objects.filter(
            players__player=user,
            status=MatchStatus.UPCOMING,
            booking__time_range__startswith__gte=now(),
            booking__time_range__startswith__lte=now() + timedelta(days=within_days),
        )
        .select_related("booking__ground__turf", "sport")
        .order_by("booking__time_range")
        .first()
    )


def nearby_sources(*, user, limit: int = 6) -> list[StockLocation]:
    """Where this player could shop: their next match's turf first, then turfs they
    have played at, then anywhere with stock."""
    from apps.ratings.models import PlayerGroundStats

    ordered: list[StockLocation] = []
    seen: set = set()

    def add(location):
        if location is not None and location.id not in seen:
            seen.add(location.id)
            ordered.append(location)

    match = next_match_for(user)
    if match is not None:
        add(StockLocation.objects.filter(turf=match.turf).first())

    profile = getattr(user, "player_profile", None)
    if profile is not None:
        played_at = (
            PlayerGroundStats.objects.filter(profile=profile)
            .order_by("-matches")
            .values_list("turf_id", flat=True)[:limit]
        )
        for turf_id in played_at:
            add(StockLocation.objects.filter(turf_id=turf_id).first())

    for location in StockLocation.objects.filter(
        is_active=True, turf__status="approved"
    ).select_related("turf")[: limit * 2]:
        add(location)
        if len(ordered) >= limit:
            break

    return ordered[:limit]


def order_queryset() -> QuerySet[Order]:
    return Order.objects.select_related(
        "location", "location__turf", "player", "address", "rider__user", "match"
    ).prefetch_related(
        Prefetch("items"),
        Prefetch("events"),
    )


def my_orders(user) -> QuerySet[Order]:
    return order_queryset().filter(player=user)


def orders_for_turf(turf) -> QuerySet[Order]:
    return order_queryset().filter(location__turf=turf)


def platform_orders() -> QuerySet[Order]:
    return order_queryset().filter(location=warehouse())


def rider_orders(rider) -> QuerySet[Order]:
    """Only what this rider was given — never the whole queue."""
    return order_queryset().filter(rider=rider).exclude(status=OrderStatus.CANCELLED)


def open_orders(queryset: QuerySet[Order]) -> QuerySet[Order]:
    return queryset.exclude(status__in=(*SETTLED_STATUSES, OrderStatus.CANCELLED))
