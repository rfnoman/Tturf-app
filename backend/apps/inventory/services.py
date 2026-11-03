"""Stock, sales and rentals (DOMAIN §9).

**The one rule**: a quantity only ever changes here, inside a transaction, with the
`StockItem` row locked, and always alongside the `StockMovement` that explains it. Views,
serializers and the admin never touch `on_hand` or `reserved`. Everything else in this
module follows from that.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils.timezone import now

from apps.notifications.models import NotificationKind
from apps.notifications.services import notify_many
from apps.turfs.services import TURF_STAFF_ROLES, has_turf_role

from .models import (
    CounterSale,
    CounterSaleLine,
    MovementType,
    Product,
    ProductKind,
    Rental,
    StockItem,
    StockLocation,
    StockMovement,
)

logger = logging.getLogger(__name__)


class OutOfStock(ValidationError):
    """Not enough available. A 409 at the API edge, not a 400: nothing is wrong with the
    request, somebody else simply got there first."""


# ---------------------------------------------------------------------------
# Locations and items
# ---------------------------------------------------------------------------
def location_for_turf(turf) -> StockLocation:
    """A turf's stock location, created on first use."""
    location, _ = StockLocation.objects.get_or_create(
        turf=turf,
        defaults={"kind": StockLocation.Kind.TURF, "name": turf.name, "address": turf.address},
    )
    return location


def warehouse() -> StockLocation:
    """The platform's single warehouse."""
    location, _ = StockLocation.objects.get_or_create(
        kind=StockLocation.Kind.WAREHOUSE,
        turf__isnull=True,
        defaults={"name": "Platform warehouse"},
    )
    return location


def get_or_create_item(*, location: StockLocation, product: Product) -> StockItem:
    item, _ = StockItem.objects.get_or_create(location=location, product=product)
    return item


def _locked(item: StockItem) -> StockItem:
    """The row, locked for this transaction.

    Re-read rather than trusted: the caller's copy was fetched before the lock, so its
    numbers may already be stale — which is the whole failure this prevents.
    """
    return StockItem.objects.select_for_update().get(pk=item.pk)


def _move(
    *,
    item: StockItem,
    type: str,
    qty_delta: int = 0,
    reserved_delta: int = 0,
    actor=None,
    reference: str = "",
    note: str = "",
) -> StockMovement:
    """Apply one change to a locked row and write the line that explains it."""
    on_hand = item.on_hand + qty_delta
    reserved = item.reserved + reserved_delta

    if on_hand < 0:
        raise OutOfStock({"quantity": f"Only {item.on_hand} of {item.product.name} on hand."})
    if reserved < 0:
        raise ValidationError({"reserved": "Cannot release more than is reserved."})
    if reserved > on_hand:
        raise OutOfStock({"quantity": f"Only {item.available} of {item.product.name} available."})

    item.on_hand = on_hand
    item.reserved = reserved
    item.save(update_fields=["on_hand", "reserved", "updated_at"])

    return StockMovement.objects.create(
        stock_item=item,
        type=type,
        qty_delta=qty_delta,
        reserved_delta=reserved_delta,
        actor=actor,
        reference=reference,
        note=note,
    )


# ---------------------------------------------------------------------------
# Receiving and adjusting
# ---------------------------------------------------------------------------
@transaction.atomic
def receive_stock(*, item: StockItem, quantity: int, actor=None, note: str = "") -> StockItem:
    """Stock arrived."""
    if quantity <= 0:
        raise ValidationError({"quantity": "Receive a positive quantity."})

    locked = _locked(item)
    _move(
        item=locked,
        type=MovementType.PURCHASE,
        qty_delta=quantity,
        actor=actor,
        note=note,
    )
    return locked


@transaction.atomic
def adjust_stock(*, item: StockItem, delta: int, reason: str, actor=None) -> StockItem:
    """A count, a breakage, an expiry. The reason is required — an unexplained
    adjustment is indistinguishable from a bug."""
    if delta == 0:
        raise ValidationError({"delta": "An adjustment of zero changes nothing."})
    if not (reason or "").strip():
        raise ValidationError({"reason": "Say why the count changed."})

    locked = _locked(item)
    _move(
        item=locked,
        type=MovementType.ADJUSTMENT,
        qty_delta=delta,
        actor=actor,
        note=reason.strip(),
    )
    check_low_stock(item=locked)
    return locked


# ---------------------------------------------------------------------------
# Reserving, for the Phase 08 store
# ---------------------------------------------------------------------------
@transaction.atomic
def reserve(*, item: StockItem, quantity: int, reference: str = "", actor=None) -> StockItem:
    """Promise stock to an order. Fails rather than overselling."""
    if quantity <= 0:
        raise ValidationError({"quantity": "Reserve a positive quantity."})

    locked = _locked(item)
    _move(
        item=locked,
        type=MovementType.RESERVATION,
        reserved_delta=quantity,
        actor=actor,
        reference=reference,
    )
    return locked


@transaction.atomic
def release(*, item: StockItem, quantity: int, reference: str = "", actor=None) -> StockItem:
    """Give a reservation back — a cancelled order, an expired hold."""
    if quantity <= 0:
        raise ValidationError({"quantity": "Release a positive quantity."})

    locked = _locked(item)
    _move(
        item=locked,
        type=MovementType.RELEASE,
        reserved_delta=-quantity,
        actor=actor,
        reference=reference,
    )
    return locked


@transaction.atomic
def commit_sale(*, item: StockItem, quantity: int, reference: str = "", actor=None) -> StockItem:
    """The reserved goods left the building: one line, both columns."""
    if quantity <= 0:
        raise ValidationError({"quantity": "Commit a positive quantity."})

    locked = _locked(item)
    if locked.reserved < quantity:
        raise ValidationError({"quantity": "That quantity was never reserved."})

    _move(
        item=locked,
        type=MovementType.SALE,
        qty_delta=-quantity,
        reserved_delta=-quantity,
        actor=actor,
        reference=reference,
    )
    check_low_stock(item=locked)
    return locked


# ---------------------------------------------------------------------------
# The counter
# ---------------------------------------------------------------------------
@transaction.atomic
def record_counter_sale(
    *,
    turf,
    staff,
    lines: list[dict],
    cash_received: Decimal | None = None,
    customer=None,
    customer_phone: str = "",
    booking=None,
    note: str = "",
) -> CounterSale:
    """Ring up a sale at the counter (DOMAIN §9).

    ``lines`` is ``[{"product": Product, "quantity": int}]``. Prices are read from the
    turf's own stock — a location price override is what a turf charges — and copied onto
    the line, because a price change next week must not rewrite last week's receipt.
    """
    if not has_turf_role(turf=turf, user=staff, roles=TURF_STAFF_ROLES):
        raise ValidationError({"staff": "Only this turf's staff can sell at its counter."})
    if not lines:
        raise ValidationError({"lines": "A sale needs at least one item."})

    location = location_for_turf(turf)
    sale = CounterSale.objects.create(
        turf=turf,
        staff=staff,
        customer=customer,
        customer_phone=customer_phone or "",
        booking=booking,
        cash_received=cash_received or Decimal("0"),
        note=note,
    )

    total = Decimal("0")
    for line in lines:
        product = line["product"]
        quantity = int(line["quantity"])
        if quantity <= 0:
            raise ValidationError({"quantity": "Every line needs a positive quantity."})
        if product.kind != ProductKind.SALE:
            raise ValidationError({"product": f"{product.name} is for rent, not for sale."})

        item = _locked(get_or_create_item(location=location, product=product))
        _move(
            item=item,
            type=MovementType.COUNTER_SALE,
            qty_delta=-quantity,
            actor=staff,
            reference=f"counter_sale:{sale.id}",
        )

        price = item.price
        CounterSaleLine.objects.create(
            sale=sale, product=product, quantity=quantity, unit_price=price
        )
        total += price * quantity
        check_low_stock(item=item)

    sale.total = total
    sale.save(update_fields=["total", "updated_at"])

    logger.info(
        "Counter sale recorded",
        extra={"sale": str(sale.id), "turf": turf.slug, "total": str(total)},
    )
    return sale


@transaction.atomic
def void_counter_sale(*, sale: CounterSale, actor, reason: str = "") -> CounterSale:
    """Undo a mis-rung sale by putting the stock back — as movements, never by deletion."""
    if not has_turf_role(turf=sale.turf, user=actor, roles=TURF_STAFF_ROLES):
        raise ValidationError({"actor": "Only this turf's staff can void its sales."})
    if sale.status != CounterSale.Status.COMPLETED:
        raise ValidationError({"status": "This sale has already been voided."})

    location = location_for_turf(sale.turf)
    for line in sale.lines.select_related("product"):
        item = _locked(get_or_create_item(location=location, product=line.product))
        _move(
            item=item,
            type=MovementType.ADJUSTMENT,
            qty_delta=line.quantity,
            actor=actor,
            reference=f"void:{sale.id}",
            note=reason or "Sale voided",
        )

    sale.status = CounterSale.Status.VOIDED
    sale.note = (sale.note + f" · voided: {reason}").strip(" ·")[:200]
    sale.save(update_fields=["status", "note", "updated_at"])
    return sale


# ---------------------------------------------------------------------------
# Rentals
# ---------------------------------------------------------------------------
@transaction.atomic
def rent_out(
    *, turf, product: Product, player, quantity: int = 1, actor=None, match=None, booking=None
) -> Rental:
    """Gear leaves the counter with a player.

    Rented stock stays `on_hand` — it is the turf's, and it is coming back — but it is
    `reserved`, so it cannot be rented to two teams at once.
    """
    if product.kind != ProductKind.RENTAL:
        raise ValidationError({"product": f"{product.name} is not rental gear."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Rent out a positive quantity."})

    item = _locked(get_or_create_item(location=location_for_turf(turf), product=product))
    rental = Rental.objects.create(
        turf=turf,
        match=match,
        booking=booking,
        player=player,
        product=product,
        quantity=quantity,
        status=Rental.Status.OUT,
        price=(product.rental_price_per_match or Decimal("0")) * quantity,
        deposit=product.deposit * quantity,
        out_at=now(),
    )
    _move(
        item=item,
        type=MovementType.RENTAL_OUT,
        reserved_delta=quantity,
        actor=actor,
        reference=f"rental:{rental.id}",
    )
    return rental


@transaction.atomic
def return_rental(*, rental: Rental, actor=None, charges: Decimal | None = None) -> Rental:
    """It came back. Any damage charge is settled against the deposit."""
    if rental.status != Rental.Status.OUT:
        raise ValidationError({"status": "This rental is not out."})

    item = _locked(
        get_or_create_item(location=location_for_turf(rental.turf), product=rental.product)
    )
    _move(
        item=item,
        type=MovementType.RENTAL_RETURN,
        reserved_delta=-rental.quantity,
        actor=actor,
        reference=f"rental:{rental.id}",
    )

    rental.status = Rental.Status.RETURNED
    rental.returned_at = now()
    rental.charges = charges or Decimal("0")
    rental.save(update_fields=["status", "returned_at", "charges", "updated_at"])
    return rental


@transaction.atomic
def mark_rental_lost(*, rental: Rental, actor=None, charges: Decimal | None = None) -> Rental:
    """It did not come back. The gear leaves stock for good and the deposit is kept."""
    if rental.status != Rental.Status.OUT:
        raise ValidationError({"status": "This rental is not out."})

    item = _locked(
        get_or_create_item(location=location_for_turf(rental.turf), product=rental.product)
    )
    _move(
        item=item,
        type=MovementType.ADJUSTMENT,
        qty_delta=-rental.quantity,
        reserved_delta=-rental.quantity,
        actor=actor,
        reference=f"rental:{rental.id}",
        note="Not returned",
    )

    rental.status = Rental.Status.LOST
    rental.charges = charges if charges is not None else rental.deposit
    rental.save(update_fields=["status", "charges", "updated_at"])
    return rental


# ---------------------------------------------------------------------------
# Low stock
# ---------------------------------------------------------------------------
def check_low_stock(*, item: StockItem) -> bool:
    """Tell the turf's staff when something is running out.

    Only on the way *down* past the line: telling somebody every time they sell one more
    water from an empty shelf trains them to ignore the alerts.
    """
    if not item.is_low or item.location.turf_id is None:
        return False

    from apps.turfs.models import TurfMembership

    staff = [
        membership.user
        for membership in TurfMembership.objects.filter(
            turf_id=item.location.turf_id,
            status=TurfMembership.Status.ACTIVE,
            role__in=TURF_STAFF_ROLES,
        ).select_related("user")
    ]
    notify_many(
        users=staff,
        kind=NotificationKind.STOCK_LOW,
        url=f"/owner/{item.location.turf.slug}/inventory",
        product=item.product.name,
        available=item.available,
        turf=item.location.turf.name,
    )
    return True


def ledger_totals(item: StockItem) -> tuple[int, int]:
    """What the movements add up to — the truth the cached columns are checked against."""
    totals = item.movements.aggregate(on_hand=Sum("qty_delta"), reserved=Sum("reserved_delta"))
    return totals["on_hand"] or 0, totals["reserved"] or 0


def low_stock_items(*, location: StockLocation):
    """Everything at or below its threshold, for the owner's dashboard."""
    return (
        StockItem.objects.filter(location=location)
        .select_related("product")
        .filter(on_hand__lte=F("reserved") + F("low_stock_threshold"))
        .order_by("product__name")
    )


#: Re-exported so Phase 08 can price a cart without reaching into models.
def price_for(*, item: StockItem) -> Decimal:
    return item.price


def settings_low_stock_default() -> int:
    return int(getattr(settings, "STOCK_LOW_DEFAULT_THRESHOLD", 5))
