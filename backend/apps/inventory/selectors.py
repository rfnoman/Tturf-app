"""Read-side queries for inventory (CLAUDE.md)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import F, QuerySet

from apps.core.utils import now

from .models import (
    CounterSale,
    OwnerType,
    Product,
    Rental,
    StockItem,
    StockLocation,
    StockMovement,
)


def product_catalogue(
    *,
    turf=None,
    category: str | None = None,
    tag: str | None = None,
    kind: str | None = None,
    sport: str | None = None,
) -> QuerySet[Product]:
    """Active products for one owner — a turf, or the platform when `turf` is None."""
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category", "turf")
        .prefetch_related("sports")
    )
    products = (
        products.filter(turf=turf)
        if turf is not None
        else products.filter(owner_type=OwnerType.PLATFORM)
    )

    if category:
        products = products.filter(category__slug=category)
    if tag:
        products = products.filter(tags__contains=[tag])
    if kind:
        products = products.filter(kind=kind)
    if sport:
        products = products.filter(sports__slug=sport)

    return products.distinct()


def stock_for(*, location: StockLocation, low_only: bool = False) -> QuerySet[StockItem]:
    items = (
        StockItem.objects.filter(location=location)
        .select_related("product", "product__category", "location")
        .prefetch_related("product__sports")
    )
    if low_only:
        items = items.filter(on_hand__lte=F("reserved") + F("low_stock_threshold"))
    return items.order_by("product__category__order", "product__name")


def movements_for(*, item: StockItem | None = None, location=None, limit: int = 200):
    """The ledger, newest first. Capped — this is a log, not an export."""
    movements = StockMovement.objects.select_related("stock_item__product", "actor").order_by(
        "-created_at"
    )
    if item is not None:
        movements = movements.filter(stock_item=item)
    if location is not None:
        movements = movements.filter(stock_item__location=location)
    return movements[:limit]


def counter_sales_for(*, turf, days: int = 1) -> QuerySet[CounterSale]:
    """Recent sales at a counter — the day's takings, by default."""
    since = now() - timedelta(days=days)
    return (
        CounterSale.objects.filter(turf=turf, created_at__gte=since)
        .select_related("staff", "turf")
        .prefetch_related("lines__product")
        .order_by("-created_at")
    )


def rentals_for(*, turf, status: str | None = None) -> QuerySet[Rental]:
    rentals = Rental.objects.filter(turf=turf).select_related("product", "player", "match")
    if status:
        rentals = rentals.filter(status=status)
    else:
        # The board is about gear that is still out; the rest is history.
        rentals = rentals.filter(status__in=[Rental.Status.RESERVED, Rental.Status.OUT])
    return rentals.order_by("-created_at")


def overdue_rentals(*, hours: int = 24) -> QuerySet[Rental]:
    """Still out long after the match ended."""
    return Rental.objects.filter(
        status=Rental.Status.OUT, out_at__lte=now() - timedelta(hours=hours)
    ).select_related("product", "player", "turf")
