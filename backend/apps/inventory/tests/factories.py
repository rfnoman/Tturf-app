"""Inventory test setup: a turf with a shelf."""

from __future__ import annotations

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.inventory.models import Product, ProductCategory, ProductKind, StockItem
from apps.inventory.services import get_or_create_item, location_for_turf, receive_stock
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfFactory, TurfMembershipFactory


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Water {n}")
    slug = factory.Sequence(lambda n: f"water-{n}")
    base_price = Decimal("25.00")
    kind = ProductKind.SALE
    category = factory.LazyFunction(lambda: ProductCategory.objects.get(slug="drinks"))


def turf_product(turf, *, name="Mineral water", price="25.00", kind=ProductKind.SALE, **extra):
    """A product on one turf's own shelf."""
    return ProductFactory(
        owner_type="turf",
        turf=turf,
        name=name,
        slug=name.lower().replace(" ", "-"),
        base_price=Decimal(price),
        kind=kind,
        **extra,
    )


def stocked_turf(*, on_hand: int = 10, price: str = "25.00") -> tuple:
    """An approved turf with a cashier and one product in stock.

    Returns ``(turf, cashier, product, item)`` — the four things nearly every test here
    needs, and in that order.
    """
    turf = TurfFactory(status="approved")
    cashier = TurfMembershipFactory(
        turf=turf, role=TurfMembership.Role.CASHIER, status=TurfMembership.Status.ACTIVE
    ).user
    product = turf_product(turf, price=price)
    item = get_or_create_item(location=location_for_turf(turf), product=product)
    if on_hand:
        receive_stock(item=item, quantity=on_hand, actor=cashier)
        item.refresh_from_db()
    return turf, cashier, product, item


def rental_product(turf, *, name="Training bibs", on_hand: int = 3):
    """Rental gear with stock behind it."""
    product = turf_product(
        turf,
        name=name,
        price="0.00",
        kind=ProductKind.RENTAL,
        rental_price_per_match=Decimal("150.00"),
        deposit=Decimal("500.00"),
        category=ProductCategory.objects.get(slug="rental"),
    )
    item = get_or_create_item(location=location_for_turf(turf), product=product)
    if on_hand:
        receive_stock(item=item, quantity=on_hand)
        item.refresh_from_db()
    return product, item


def reload(item: StockItem) -> StockItem:
    item.refresh_from_db()
    return item
