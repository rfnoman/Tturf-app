"""The store: carts, orders and delivery (DOMAIN §9).

Two rules shape everything here.

**One order has one stock source.** A cart may hold the platform's whey protein and a
turf's bananas, but they are picked, paid for and delivered by different people, so
checkout splits them into one order each. `Order.location` is that source.

**What a player may choose depends on where the goods are.** Turf stock is pickup only
(D4); platform stock can reach a turf only before the cutoff (D5) and only for a match
the player is actually in. The matrix lives in `services.fulfilment_options`, and the
reasons an option is unavailable are part of its answer — "not available" without a
reason is how a store loses a sale.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.inventory.models import Product, StockItem, StockLocation


class Fulfilment(models.TextChoices):
    PICKUP_AT_TURF = "pickup_at_turf", _("Pick up at the turf")
    DELIVER_TO_TURF = "deliver_to_turf", _("Delivered to the turf for a match")
    DELIVER_TO_ADDRESS = "deliver_to_address", _("Delivered to an address")


class OrderStatus(models.TextChoices):
    PLACED = "placed", _("Placed")
    ACCEPTED = "accepted", _("Accepted")
    PACKED = "packed", _("Packed")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for delivery")
    READY_FOR_PICKUP = "ready_for_pickup", _("Ready for pickup")
    DELIVERED = "delivered", _("Delivered")
    PICKED_UP = "picked_up", _("Picked up")
    CANCELLED = "cancelled", _("Cancelled")


#: Stock is committed on these, released on cancellation, and held in between.
SETTLED_STATUSES = (OrderStatus.DELIVERED, OrderStatus.PICKED_UP)
#: A player may still call it off up to here; after packing somebody has done the work.
PLAYER_CANCELLABLE = (OrderStatus.PLACED, OrderStatus.ACCEPTED)


class PaymentMethod(models.TextChoices):
    CASH_ON_DELIVERY = "cod", _("Cash on delivery")
    PAY_AT_PICKUP = "pay_at_pickup", _("Pay at pickup")


class DeliveryZone(BaseModel):
    """Where the platform delivers, what it charges, and how long it takes."""

    name = models.CharField(_("name"), max_length=120)
    areas = models.JSONField(
        _("areas"),
        default=list,
        blank=True,
        help_text='Area names this zone covers, e.g. ["Dhanmondi", "Mirpur"].',
    )
    boundary = gis.PolygonField(
        _("boundary"),
        srid=4326,
        null=True,
        blank=True,
        help_text="Optional precise boundary; the area list is the fallback.",
    )
    fee = models.DecimalField(
        _("delivery fee"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    eta_hours = models.PositiveSmallIntegerField(_("ETA (hours)"), default=4)
    turf_delivery_cutoff_hours = models.PositiveSmallIntegerField(
        _("turf delivery cutoff (hours)"),
        null=True,
        blank=True,
        help_text="Overrides TURF_DELIVERY_CUTOFF_HOURS for this zone (DECISIONS D5).",
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("delivery zone")
        verbose_name_plural = _("delivery zones")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def covers(self, *, area: str = "", point=None) -> bool:
        """Does this zone cover that address?

        The polygon wins when there is one and the address has a point; otherwise the
        area name decides, because that is what a Dhaka address actually carries.
        """
        if self.boundary is not None and point is not None:
            return self.boundary.contains(point)
        if not area:
            return False
        return any(area.strip().lower() == name.strip().lower() for name in self.areas or [])


class Address(BaseModel):
    """Somewhere a player has things delivered."""

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(_("label"), max_length=40, blank=True, help_text='e.g. "Home".')
    line = models.CharField(_("address"), max_length=255)
    area = models.CharField(_("area"), max_length=120)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    location = gis.PointField(_("location"), srid=4326, null=True, blank=True)
    is_default = models.BooleanField(_("default"), default=False)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "label", "line"]

    def __str__(self) -> str:
        return f"{self.label or self.area}: {self.line}"


class Cart(BaseModel):
    """One open cart per player. Items may come from several sources."""

    player = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")

    def __str__(self) -> str:
        return f"Cart of {self.player}"


class CartItem(BaseModel):
    """A line in the cart, pointing at *stock*, not just a product.

    The same product can sit in the warehouse and on three turfs' shelves at different
    prices; which one the player is buying is the thing that matters at checkout.
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "stock_item"], name="unique_item_per_cart"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.stock_item.product.name}"


class RiderProfile(BaseModel):
    """Somebody who delivers platform orders."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rider_profile"
    )
    zones = models.ManyToManyField(DeliveryZone, related_name="riders", blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("rider")
        verbose_name_plural = _("riders")

    def __str__(self) -> str:
        return self.user.full_name or self.user.email


class Order(BaseModel):
    """One order, from one source, with one way of reaching the player."""

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="orders",
        help_text="Where the goods come from. One order, one source (DOMAIN §9).",
    )
    fulfilment = models.CharField(_("fulfilment"), max_length=20, choices=Fulfilment.choices)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Required for delivery to a turf; optional for a pickup.",
    )
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    zone = models.ForeignKey(
        DeliveryZone, on_delete=models.PROTECT, null=True, blank=True, related_name="orders"
    )

    subtotal = models.DecimalField(_("subtotal"), max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(
        _("delivery fee"), max_digits=12, decimal_places=2, default=0
    )
    total = models.DecimalField(_("total"), max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(
        _("payment"),
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH_ON_DELIVERY,
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PLACED,
        db_index=True,
    )
    rider = models.ForeignKey(
        RiderProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    scheduled_for = models.DateTimeField(
        _("needed by"),
        null=True,
        blank=True,
        help_text="Kick-off, for an order going to a match.",
    )
    notes = models.CharField(_("notes"), max_length=300, blank=True)
    settled_at = models.DateTimeField(_("settled at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancel_reason = models.CharField(_("cancellation reason"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["player", "-created_at"], name="order_player_idx"),
            models.Index(fields=["location", "status"], name="order_location_status_idx"),
            models.Index(fields=["status", "scheduled_for"], name="order_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(fulfilment=Fulfilment.DELIVER_TO_ADDRESS)
                    | models.Q(address__isnull=False)
                ),
                name="address_delivery_needs_an_address",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(fulfilment=Fulfilment.DELIVER_TO_TURF) | models.Q(match__isnull=False)
                ),
                name="turf_delivery_needs_a_match",
            ),
        ]

    def __str__(self) -> str:
        return f"৳{self.total} from {self.location.name}"

    @property
    def is_delivery(self) -> bool:
        return self.fulfilment != Fulfilment.PICKUP_AT_TURF

    @property
    def is_open(self) -> bool:
        return self.status not in (*SETTLED_STATUSES, OrderStatus.CANCELLED)


class OrderItem(BaseModel):
    """A line, snapshotted.

    Name, price and nutrition are copied at checkout: a receipt has to keep saying what
    was bought and what it cost, whatever the catalogue does afterwards.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    stock_item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="order_items")
    name = models.CharField(_("name"), max_length=120)
    unit_price = models.DecimalField(_("unit price"), max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(_("quantity"), validators=[MinValueValidator(1)])
    nutrition = models.JSONField(_("nutrition"), default=dict, blank=True)

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderEvent(BaseModel):
    """The order's history, the same pattern as bookings and scorecards."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(
        _("from"), max_length=20, choices=OrderStatus.choices, blank=True
    )
    to_status = models.CharField(_("to"), max_length=20, choices=OrderStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_events",
    )
    note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("order event")
        verbose_name_plural = _("order events")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.from_status or 'new'} → {self.to_status}"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
ORDER_STATUS_CHOICES = OrderStatus.choices
ORDER_FULFILMENT_CHOICES = Fulfilment.choices
ORDER_PAYMENT_METHOD_CHOICES = PaymentMethod.choices
