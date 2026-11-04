"""Carts, the fulfilment matrix, checkout and the order lifecycle (DOMAIN §9)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now

from apps.inventory.models import StockItem, StockLocation
from apps.inventory.services import OutOfStock, commit_sale, release, reserve
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify, notify_many
from apps.payments.models import Payment, PaymentStatus
from apps.payments.models import PaymentMethod as PayMethod

from .models import (
    PLAYER_CANCELLABLE,
    Address,
    Cart,
    CartItem,
    DeliveryZone,
    Fulfilment,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    RiderProfile,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The cart
# ---------------------------------------------------------------------------
def get_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(player=user)
    return cart


@transaction.atomic
def add_to_cart(*, user, stock_item: StockItem, quantity: int = 1) -> CartItem:
    """Put something in the cart.

    Availability is checked here as a courtesy, not as a promise: nothing is held until
    checkout, so a popular item can still sell out between the two. Checkout is where
    that becomes a refusal.
    """
    if quantity <= 0:
        raise ValidationError({"quantity": "Add at least one."})
    if not stock_item.product.is_active:
        raise ValidationError({"product": "That product is not for sale."})
    if stock_item.product.is_rental:
        raise ValidationError({"product": "Rental gear is arranged at the turf, not ordered."})

    cart = get_cart(user)
    item, created = CartItem.objects.get_or_create(
        cart=cart, stock_item=stock_item, defaults={"quantity": quantity}
    )
    if not created:
        item.quantity += quantity
    if item.quantity > stock_item.available:
        raise OutOfStock(
            {"quantity": f"Only {stock_item.available} of {stock_item.product.name} left."}
        )
    item.save()
    return item


@transaction.atomic
def set_cart_quantity(*, user, stock_item: StockItem, quantity: int) -> CartItem | None:
    """Set a line's quantity. Zero removes it."""
    cart = get_cart(user)
    item = CartItem.objects.filter(cart=cart, stock_item=stock_item).first()
    if item is None:
        return (
            None
            if quantity <= 0
            else add_to_cart(user=user, stock_item=stock_item, quantity=quantity)
        )

    if quantity <= 0:
        item.delete()
        return None
    if quantity > stock_item.available:
        raise OutOfStock(
            {"quantity": f"Only {stock_item.available} of {stock_item.product.name} left."}
        )
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def clear_cart(*, user) -> int:
    deleted, _ = CartItem.objects.filter(cart__player=user).delete()
    return deleted


def cart_by_source(*, user) -> dict[StockLocation, list[CartItem]]:
    """The cart grouped the way it will be ordered: one group per source."""
    groups: dict[StockLocation, list[CartItem]] = {}
    items = (
        CartItem.objects.filter(cart__player=user)
        .select_related(
            "stock_item__location__turf", "stock_item__product", "stock_item__product__category"
        )
        .order_by("created_at")
    )
    for item in items:
        groups.setdefault(item.stock_item.location, []).append(item)
    return groups


# ---------------------------------------------------------------------------
# The fulfilment matrix (DOMAIN §9, DECISIONS D4 and D5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FulfilmentOption:
    """One way of getting an order to a player, and whether it is open to them."""

    kind: str
    available: bool
    fee: Decimal = Decimal("0")
    eta_hours: int | None = None
    #: Why not, in words a shopper can act on. Empty when `available`.
    reason: str = ""
    #: When `deliver_to_turf` stops being possible for the match in question.
    cutoff_at = None


def cutoff_hours(zone: DeliveryZone | None = None) -> int:
    """How long before kick-off the platform stops promising delivery to a turf (D5)."""
    if zone is not None and zone.turf_delivery_cutoff_hours is not None:
        return int(zone.turf_delivery_cutoff_hours)
    return int(settings.TURF_DELIVERY_CUTOFF_HOURS)


def zone_for(*, area: str = "", point=None) -> DeliveryZone | None:
    """The first active zone covering an address, or None if nobody delivers there."""
    for zone in DeliveryZone.objects.filter(is_active=True).order_by("fee", "name"):
        if zone.covers(area=area, point=point):
            return zone
    return None


def _has_perishable(items) -> bool:
    return any(item.stock_item.product.perishable for item in items)


def fulfilment_options(
    *,
    user,
    location: StockLocation,
    items=(),
    match=None,
    address: Address | None = None,
) -> list[FulfilmentOption]:
    """Every option for one source, each either open or refused with a reason.

    This is the DOMAIN §9 matrix in one place:

    * **Turf stock** → pickup only (D4). Delivery from a turf waits for a later release.
    * **Platform stock → a turf** → only for a match this player is on, and only while
      there is more than the cutoff left before kick-off (D5).
    * **Platform stock → an address** → any time, for a fee set by the zone; refused
      politely when nobody delivers there.

    A perishable from a turf is pickup only whatever else is true.
    """
    is_turf = location.turf_id is not None
    options: list[FulfilmentOption] = []

    if is_turf:
        options.append(
            FulfilmentOption(kind=Fulfilment.PICKUP_AT_TURF, available=True, eta_hours=0)
        )
        options.append(
            FulfilmentOption(
                kind=Fulfilment.DELIVER_TO_TURF,
                available=False,
                reason="It is already at the turf — pick it up there.",
            )
        )
        options.append(
            FulfilmentOption(
                kind=Fulfilment.DELIVER_TO_ADDRESS,
                available=False,
                reason="This turf does not deliver yet. Pick it up at the counter.",
            )
        )
        return options

    # Platform stock: never collected in person, because there is no counter to collect
    # from — the warehouse is not a shop.
    options.append(
        FulfilmentOption(
            kind=Fulfilment.PICKUP_AT_TURF,
            available=False,
            reason="The platform store delivers; there is nothing to pick up.",
        )
    )

    zone = None
    if address is not None:
        zone = zone_for(area=address.area, point=address.location)

    options.append(_to_turf_option(user=user, match=match, zone=zone))

    if address is None:
        options.append(
            FulfilmentOption(
                kind=Fulfilment.DELIVER_TO_ADDRESS,
                available=False,
                reason="Choose an address to see the delivery charge.",
            )
        )
    elif zone is None:
        options.append(
            FulfilmentOption(
                kind=Fulfilment.DELIVER_TO_ADDRESS,
                available=False,
                reason=f"We do not deliver to {address.area} yet.",
            )
        )
    else:
        options.append(
            FulfilmentOption(
                kind=Fulfilment.DELIVER_TO_ADDRESS,
                available=True,
                fee=zone.fee,
                eta_hours=zone.eta_hours,
            )
        )

    if items and _has_perishable(items):
        # Platform perishables are not part of v1; the catalogue has none, and this
        # makes that explicit rather than accidental.
        options = [
            option
            if option.kind != Fulfilment.DELIVER_TO_TURF
            else FulfilmentOption(
                kind=option.kind,
                available=False,
                reason="Fresh items are pickup only.",
            )
            for option in options
        ]

    return options


def _to_turf_option(*, user, match, zone) -> FulfilmentOption:
    if match is None:
        return FulfilmentOption(
            kind=Fulfilment.DELIVER_TO_TURF,
            available=False,
            reason="Pick one of your upcoming matches to have it sent to the turf.",
        )

    if not match.players.filter(player=user).exists():
        return FulfilmentOption(
            kind=Fulfilment.DELIVER_TO_TURF,
            available=False,
            reason="You are not playing in that match.",
        )

    hours = cutoff_hours(zone)
    deadline = match.starts_at - timedelta(hours=hours)
    if now() > deadline:
        return FulfilmentOption(
            kind=Fulfilment.DELIVER_TO_TURF,
            available=False,
            reason=(f"Too late for this one — orders have to be in {hours} hours before kick-off."),
        )

    return FulfilmentOption(
        kind=Fulfilment.DELIVER_TO_TURF, available=True, eta_hours=hours, fee=Decimal("0")
    )


def option_for(options, kind: str) -> FulfilmentOption | None:
    return next((option for option in options if option.kind == kind), None)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------
def _nutrition_snapshot(product) -> dict:
    return {
        "serving_size": product.serving_size,
        "calories": product.calories,
        "protein_g": str(product.protein_g) if product.protein_g is not None else None,
        "carbs_g": str(product.carbs_g) if product.carbs_g is not None else None,
        "fat_g": str(product.fat_g) if product.fat_g is not None else None,
        "sugar_g": str(product.sugar_g) if product.sugar_g is not None else None,
        "caffeine_mg": product.caffeine_mg,
    }


@transaction.atomic
def checkout(*, user, choices: dict) -> list[Order]:
    """Turn the cart into orders — one per source — holding the stock as it goes.

    ``choices`` is ``{location_id: {"fulfilment": ..., "match": Match|None,
    "address": Address|None, "notes": str}}``.

    All or nothing: if the last line of the second order is out of stock, the first
    order is rolled back too. A player who was told "ordered" and finds half of it
    missing has been lied to, and a half-reserved shelf is worse than a refusal.
    """
    groups = cart_by_source(user=user)
    if not groups:
        raise ValidationError({"cart": "Your cart is empty."})

    orders = []
    for location, items in groups.items():
        choice = choices.get(str(location.id)) or choices.get(location.id)
        if choice is None:
            raise ValidationError(
                {"fulfilment": f"Choose how to get the items from {location.name}."}
            )

        kind = choice.get("fulfilment")
        match = choice.get("match")
        address = choice.get("address")

        options = fulfilment_options(
            user=user, location=location, items=items, match=match, address=address
        )
        chosen = option_for(options, kind)
        if chosen is None or not chosen.available:
            raise ValidationError(
                {"fulfilment": chosen.reason if chosen else "That is not an option here."}
            )

        order = Order.objects.create(
            player=user,
            location=location,
            fulfilment=kind,
            match=match if kind != Fulfilment.DELIVER_TO_ADDRESS else None,
            address=address if kind == Fulfilment.DELIVER_TO_ADDRESS else None,
            zone=zone_for(area=address.area, point=address.location) if address else None,
            delivery_fee=chosen.fee,
            payment_method=(
                PaymentMethod.PAY_AT_PICKUP
                if kind == Fulfilment.PICKUP_AT_TURF
                else PaymentMethod.CASH_ON_DELIVERY
            ),
            scheduled_for=match.starts_at if match else None,
            notes=(choice.get("notes") or "")[:300],
        )

        subtotal = Decimal("0")
        for item in items:
            stock_item = item.stock_item
            product = stock_item.product
            # Reserving is what makes this real; it raises OutOfStock if somebody else
            # got there first, and the whole checkout rolls back.
            reserve(
                item=stock_item,
                quantity=item.quantity,
                reference=f"order:{order.id}",
                actor=user,
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                stock_item=stock_item,
                name=product.name,
                unit_price=stock_item.price,
                quantity=item.quantity,
                nutrition=_nutrition_snapshot(product),
            )
            subtotal += stock_item.price * item.quantity

        order.subtotal = subtotal
        order.total = subtotal + order.delivery_fee
        order.save(update_fields=["subtotal", "total", "updated_at"])

        _record_event(order=order, previous="", actor=user, note="Order placed")
        _notify_source(order)
        orders.append(order)

    clear_cart(user=user)
    logger.info("Checkout complete", extra={"orders": len(orders), "user": str(user.id)})
    return orders


def _record_event(*, order: Order, previous: str, actor=None, note: str = "") -> OrderEvent:
    return OrderEvent.objects.create(
        order=order, from_status=previous, to_status=order.status, actor=actor, note=note
    )


def _notify_source(order: Order) -> None:
    """Tell whoever has to act: a turf's staff, or the platform's admins."""
    from apps.accounts.models import User
    from apps.turfs.models import TurfMembership
    from apps.turfs.services import TURF_STAFF_ROLES

    if order.location.turf_id is not None:
        recipients = [
            membership.user
            for membership in TurfMembership.objects.filter(
                turf_id=order.location.turf_id,
                status=TurfMembership.Status.ACTIVE,
                role__in=TURF_STAFF_ROLES,
            ).select_related("user")
        ]
        url = f"/owner/{order.location.turf.slug}/orders"
    else:
        recipients = list(User.objects.filter(is_platform_admin=True))
        url = "/admin/orders"

    notify_many(
        users=recipients,
        kind=NotificationKind.ORDER_PLACED,
        url=url,
        total=f"৳{order.total}",
        source=order.location.name,
        items=order.items.count(),
    )


# ---------------------------------------------------------------------------
# The order lifecycle
# ---------------------------------------------------------------------------
def can_manage(*, order: Order, user) -> bool:
    """Whoever is responsible for the goods: the turf's staff, or a platform admin."""
    if getattr(user, "is_platform_admin", False) or getattr(user, "is_superuser", False):
        return True
    if order.location.turf_id is None:
        return False

    from apps.turfs.services import TURF_STAFF_ROLES, has_turf_role

    return has_turf_role(turf=order.location.turf, user=user, roles=TURF_STAFF_ROLES)


def _transition(*, order: Order, to: str, actor, allowed_from: tuple, note: str = "") -> Order:
    if order.status not in allowed_from:
        raise ValidationError(
            {"status": f"An order that is {order.get_status_display().lower()} cannot do that."}
        )
    previous = order.status
    order.status = to
    order.save(update_fields=["status", "updated_at"])
    _record_event(order=order, previous=previous, actor=actor, note=note)
    return order


@transaction.atomic
def accept_order(*, order: Order, actor) -> Order:
    if not can_manage(order=order, user=actor):
        raise ValidationError({"actor": "Only the source can accept this order."})
    order = _transition(
        order=order, to=OrderStatus.ACCEPTED, actor=actor, allowed_from=(OrderStatus.PLACED,)
    )
    notify(
        user=order.player,
        kind=NotificationKind.ORDER_ACCEPTED,
        url=f"/orders/{order.id}",
        source=order.location.name,
        total=f"৳{order.total}",
    )
    return order


@transaction.atomic
def pack_order(*, order: Order, actor) -> Order:
    if not can_manage(order=order, user=actor):
        raise ValidationError({"actor": "Only the source can pack this order."})
    return _transition(
        order=order,
        to=OrderStatus.PACKED,
        actor=actor,
        allowed_from=(OrderStatus.PLACED, OrderStatus.ACCEPTED),
    )


@transaction.atomic
def assign_rider(*, order: Order, rider: RiderProfile, actor) -> Order:
    if not can_manage(order=order, user=actor):
        raise ValidationError({"actor": "Only the source can assign a rider."})
    if not order.is_delivery:
        raise ValidationError({"rider": "A pickup does not need a rider."})
    if not rider.is_active:
        raise ValidationError({"rider": "That rider is not taking deliveries."})

    order.rider = rider
    order.save(update_fields=["rider", "updated_at"])
    _record_event(order=order, previous=order.status, actor=actor, note=f"Rider: {rider}")
    notify(
        user=rider.user,
        kind=NotificationKind.ORDER_ASSIGNED,
        url=f"/rider/{order.id}",
        total=f"৳{order.total}",
        where=order.address.area if order.address else order.location.name,
    )
    return order


@transaction.atomic
def mark_out_for_delivery(*, order: Order, actor) -> Order:
    if not (can_manage(order=order, user=actor) or _is_rider(order=order, user=actor)):
        raise ValidationError({"actor": "Only the source or the rider can do that."})
    if not order.is_delivery:
        raise ValidationError({"status": "A pickup is never out for delivery."})
    return _transition(
        order=order,
        to=OrderStatus.OUT_FOR_DELIVERY,
        actor=actor,
        allowed_from=(OrderStatus.ACCEPTED, OrderStatus.PACKED),
    )


@transaction.atomic
def mark_ready_for_pickup(*, order: Order, actor) -> Order:
    if not can_manage(order=order, user=actor):
        raise ValidationError({"actor": "Only the turf can do that."})
    if order.fulfilment != Fulfilment.PICKUP_AT_TURF:
        raise ValidationError({"status": "That order is being delivered."})
    order = _transition(
        order=order,
        to=OrderStatus.READY_FOR_PICKUP,
        actor=actor,
        allowed_from=(OrderStatus.ACCEPTED, OrderStatus.PACKED),
    )
    notify(
        user=order.player,
        kind=NotificationKind.ORDER_READY,
        url=f"/orders/{order.id}",
        source=order.location.name,
    )
    return order


def _is_rider(*, order: Order, user) -> bool:
    return order.rider is not None and order.rider.user_id == getattr(user, "id", None)


@transaction.atomic
def settle_order(*, order: Order, actor, cash_received: Decimal | None = None) -> Order:
    """Delivered or picked up: the goods leave stock and the money is recorded.

    One function for both endings because they are the same event — the player has the
    goods and has paid. Which word to use is decided by how it was fulfilled.
    """
    if not (can_manage(order=order, user=actor) or _is_rider(order=order, user=actor)):
        raise ValidationError({"actor": "Only the source or the rider can do that."})

    to = (
        OrderStatus.PICKED_UP
        if order.fulfilment == Fulfilment.PICKUP_AT_TURF
        else OrderStatus.DELIVERED
    )
    order = _transition(
        order=order,
        to=to,
        actor=actor,
        # `placed` is allowed on purpose: a player who orders at the counter and takes
        # it straight away should not need the staff to tap "accept" first. Handing the
        # goods over *is* the acceptance, and the event log still records the jump.
        allowed_from=(
            OrderStatus.PLACED,
            OrderStatus.ACCEPTED,
            OrderStatus.PACKED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.READY_FOR_PICKUP,
        ),
    )

    for item in order.items.select_related("stock_item"):
        commit_sale(
            item=item.stock_item,
            quantity=item.quantity,
            reference=f"order:{order.id}",
            actor=actor,
        )

    Payment.objects.create(
        order=order,
        amount=order.total,
        method=PayMethod.CASH,
        status=PaymentStatus.PAID,
        collected_by=actor,
        collected_at=now(),
        note=f"{order.get_fulfilment_display()} · ৳{cash_received or order.total} received",
    )

    order.settled_at = now()
    order.save(update_fields=["settled_at", "updated_at"])

    notify(
        user=order.player,
        kind=NotificationKind.ORDER_DELIVERED,
        url=f"/orders/{order.id}",
        source=order.location.name,
        total=f"৳{order.total}",
    )
    return order


@transaction.atomic
def cancel_order(*, order: Order, actor, reason: str = "") -> Order:
    """Call it off and give the stock back.

    A player may cancel until it is packed; after that somebody has done the work, and
    only the source can.
    """
    # Checked first: a delivered order is finished, not "being prepared", and telling a
    # player to ring the turf about something they already have is nonsense.
    if not order.is_open:
        raise ValidationError({"status": "This order is already finished."})

    is_player = order.player_id == getattr(actor, "id", None)
    if is_player and order.status not in PLAYER_CANCELLABLE:
        raise ValidationError(
            {"status": "This order is already being prepared — call the turf instead."}
        )
    if not is_player and not can_manage(order=order, user=actor):
        raise ValidationError({"actor": "You cannot cancel this order."})

    previous = order.status
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now()
    order.cancel_reason = (reason or "").strip()[:200]
    order.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
    _record_event(order=order, previous=previous, actor=actor, note=order.cancel_reason)

    for item in order.items.select_related("stock_item"):
        release(
            item=item.stock_item,
            quantity=item.quantity,
            reference=f"order:{order.id}",
            actor=actor,
        )

    notify(
        user=order.player,
        kind=NotificationKind.ORDER_CANCELLED,
        url=f"/orders/{order.id}",
        source=order.location.name,
        reason=order.cancel_reason or "No reason given",
    )
    return order
