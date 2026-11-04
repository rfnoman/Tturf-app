"""Products, stock and the counter (DOMAIN §9).

The shape of this app is one idea: **`StockItem` is a cache of `StockMovement`.** Every
change to a quantity is a movement row written in the same transaction as the update,
under a row lock, by a service — never by a view, a serializer or the admin. That is what
makes "where did my 30 waters go?" a question with an answer, and it is asserted by a
test that replays the ledger and compares it with the cached totals.

Two kinds of owner share one catalogue: the platform (sold through the Phase 08 store)
and a turf (sold at its counter, or delivered to a match there). A product belongs to one
of them, and `StockLocation` mirrors that split.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.utils import in_readers_language
from apps.sports.models import Sport
from apps.turfs.models import Turf


class OwnerType(models.TextChoices):
    PLATFORM = "platform", _("Platform")
    TURF = "turf", _("Turf")


class ProductKind(models.TextChoices):
    SALE = "sale", _("For sale")
    RENTAL = "rental", _("For rent")


#: Fitness-facing tags (DOMAIN §9). Kept as a list of slugs rather than a table: they are
#: a fixed vocabulary the store filters on, not something a turf invents.
PRODUCT_TAGS = (
    "hydration",
    "recovery",
    "pre_match",
    "protein",
    "low_sugar",
    "vegan",
    "gear",
)


class ProductCategory(BaseModel):
    """Drinks, food, gear… Seeded, and shared by both owners."""

    slug = models.SlugField(_("slug"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=60)
    label_bn = models.CharField(
        _("label (Bangla)"),
        max_length=60,
        blank=True,
        help_text="Shown to Bangla readers. Blank falls back to the English label.",
    )
    icon = models.CharField(_("icon"), max_length=8, blank=True)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    #: Nutrition is asked for on food and drink and nowhere else.
    is_consumable = models.BooleanField(_("consumable"), default=False)

    class Meta:
        verbose_name = _("product category")
        verbose_name_plural = _("product categories")
        ordering = ["order", "label"]

    def __str__(self) -> str:
        return self.label

    @property
    def display_label(self) -> str:
        """The label in the reader's language. Serializers expose this, never `label`."""
        return in_readers_language(self, "label")


class Product(BaseModel):
    """Something sold or rented, owned by the platform or by one turf."""

    owner_type = models.CharField(
        _("owner"), max_length=10, choices=OwnerType.choices, default=OwnerType.TURF
    )
    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name="products",
        null=True,
        blank=True,
        help_text="Null for the platform catalogue.",
    )
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="products")

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140)
    description = models.TextField(_("description"), max_length=1000, blank=True)
    image_url = models.URLField(_("image"), blank=True)

    kind = models.CharField(
        _("kind"), max_length=8, choices=ProductKind.choices, default=ProductKind.SALE
    )
    base_price = models.DecimalField(
        _("price"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="BDT. A stock item may override it for one location.",
    )
    rental_price_per_match = models.DecimalField(
        _("rental price per match"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    deposit = models.DecimalField(
        _("deposit"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Held against a rental and returned with the gear.",
    )

    perishable = models.BooleanField(
        _("perishable"),
        default=False,
        help_text="DOMAIN §9: a turf's perishables are pickup only, never delivered.",
    )
    sku = models.CharField(_("SKU"), max_length=40, blank=True)
    barcode = models.CharField(
        _("barcode"), max_length=40, blank=True, db_index=True, help_text="Scanned at the counter."
    )

    # Nutrition, for the Phase 09 fitness layer. Null means "not applicable", which is
    # not the same as zero.
    serving_size = models.CharField(_("serving size"), max_length=40, blank=True)
    calories = models.PositiveIntegerField(_("calories"), null=True, blank=True)
    protein_g = models.DecimalField(
        _("protein (g)"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    carbs_g = models.DecimalField(
        _("carbs (g)"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    fat_g = models.DecimalField(_("fat (g)"), max_digits=6, decimal_places=1, null=True, blank=True)
    sugar_g = models.DecimalField(
        _("sugar (g)"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    caffeine_mg = models.PositiveIntegerField(_("caffeine (mg)"), null=True, blank=True)

    tags = models.JSONField(
        _("tags"), default=list, blank=True, help_text=f"Any of: {', '.join(PRODUCT_TAGS)}."
    )
    sports = models.ManyToManyField(
        Sport, related_name="products", blank=True, help_text="Where this gear is relevant."
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["category__order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["turf", "slug"],
                name="unique_product_slug_per_turf",
                condition=models.Q(turf__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["slug"],
                name="unique_platform_product_slug",
                condition=models.Q(turf__isnull=True),
            ),
            # The owner and the turf have to agree, or "whose product is this?" has two
            # answers and the store shows it in the wrong section.
            models.CheckConstraint(
                condition=(
                    models.Q(owner_type=OwnerType.PLATFORM, turf__isnull=True)
                    | models.Q(owner_type=OwnerType.TURF, turf__isnull=False)
                ),
                name="product_owner_matches_turf",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_type", "is_active"], name="product_owner_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_rental(self) -> bool:
        return self.kind == ProductKind.RENTAL


class StockLocation(BaseModel):
    """Where stock sits: the platform warehouse, or a turf."""

    class Kind(models.TextChoices):
        WAREHOUSE = "warehouse", _("Platform warehouse")
        TURF = "turf", _("Turf")

    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices)
    turf = models.OneToOneField(
        Turf, on_delete=models.CASCADE, related_name="stock_location", null=True, blank=True
    )
    name = models.CharField(_("name"), max_length=120)
    address = models.CharField(_("address"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("stock location")
        verbose_name_plural = _("stock locations")
        ordering = ["kind", "name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="warehouse", turf__isnull=True)
                    | models.Q(kind="turf", turf__isnull=False)
                ),
                name="stock_location_kind_matches_turf",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StockItem(BaseModel):
    """One product at one location.

    ``on_hand`` is everything physically there; ``reserved`` is the part already promised
    to an order or a rental. What a shopper may buy is the difference — see
    :attr:`available`.
    """

    location = models.ForeignKey(StockLocation, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_items")
    on_hand = models.IntegerField(_("on hand"), default=0)
    reserved = models.IntegerField(_("reserved"), default=0)
    price_override = models.DecimalField(
        _("price at this location"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    low_stock_threshold = models.PositiveIntegerField(
        _("low stock threshold"),
        default=5,
        help_text="At or below this, the owner is told to restock.",
    )

    class Meta:
        verbose_name = _("stock item")
        verbose_name_plural = _("stock items")
        ordering = ["product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "product"], name="unique_product_per_location"
            ),
            models.CheckConstraint(condition=models.Q(on_hand__gte=0), name="stock_not_negative"),
            models.CheckConstraint(
                condition=models.Q(reserved__gte=0), name="reserved_not_negative"
            ),
            # Reserving more than is there would promise stock that does not exist.
            models.CheckConstraint(
                condition=models.Q(reserved__lte=models.F("on_hand")),
                name="reserved_within_on_hand",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} @ {self.location.name}"

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    @property
    def price(self):
        return self.price_override if self.price_override is not None else self.product.base_price

    @property
    def is_low(self) -> bool:
        return self.available <= self.low_stock_threshold


class MovementType(models.TextChoices):
    PURCHASE = "purchase", _("Stock received")
    SALE = "sale", _("Sold (online)")
    COUNTER_SALE = "counter_sale", _("Sold at the counter")
    RESERVATION = "reservation", _("Reserved")
    RELEASE = "release", _("Reservation released")
    RENTAL_OUT = "rental_out", _("Rented out")
    RENTAL_RETURN = "rental_return", _("Rental returned")
    ADJUSTMENT = "adjustment", _("Adjusted")


class StockMovement(BaseModel):
    """One append-only line of the ledger.

    Never edited and never deleted: a correction is another movement. ``qty_delta`` moves
    ``on_hand`` and ``reserved_delta`` moves ``reserved``, so one row can express
    "committed a reservation" (−1 on hand, −1 reserved) without two half-truths.
    """

    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="movements")
    type = models.CharField(_("type"), max_length=14, choices=MovementType.choices)
    qty_delta = models.IntegerField(_("quantity change"))
    reserved_delta = models.IntegerField(_("reserved change"), default=0)
    reference = models.CharField(
        _("reference"),
        max_length=80,
        blank=True,
        help_text='What caused it, e.g. "counter_sale:3f2b…" or "order:9c1a…".',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("stock movement")
        verbose_name_plural = _("stock movements")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stock_item", "-created_at"], name="movement_item_idx"),
            models.Index(fields=["reference"], name="movement_reference_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.qty_delta:+d}"


class CounterSale(BaseModel):
    """A sale rung up at the turf's counter (DOMAIN §9)."""

    class Status(models.TextChoices):
        COMPLETED = "completed", _("Completed")
        VOIDED = "voided", _("Voided")

    turf = models.ForeignKey(Turf, on_delete=models.PROTECT, related_name="counter_sales")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="counter_sales"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counter_purchases",
        help_text="Set when the buyer has an account; most counter sales will not.",
    )
    customer_phone = models.CharField(_("customer phone"), max_length=32, blank=True)
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counter_sales",
        help_text="Attached when the sale belongs to a game being played.",
    )
    total = models.DecimalField(_("total"), max_digits=12, decimal_places=2, default=0)
    cash_received = models.DecimalField(
        _("cash received"), max_digits=12, decimal_places=2, default=0
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.COMPLETED
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("counter sale")
        verbose_name_plural = _("counter sales")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["turf", "-created_at"], name="counter_sale_turf_idx"),
        ]

    def __str__(self) -> str:
        return f"৳{self.total} at {self.turf.name}"

    @property
    def change_due(self):
        return max(self.cash_received - self.total, 0)


class CounterSaleLine(BaseModel):
    """One line of a counter sale, priced when it was rung up."""

    sale = models.ForeignKey(CounterSale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="counter_lines")
    quantity = models.PositiveIntegerField(_("quantity"), validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        _("unit price"),
        max_digits=12,
        decimal_places=2,
        help_text="Copied at the time of sale: a later price change must not rewrite history.",
    )

    class Meta:
        verbose_name = _("counter sale line")
        verbose_name_plural = _("counter sale lines")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product.name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Rental(BaseModel):
    """Gear taken out for a match and brought back (DOMAIN §9)."""

    class Status(models.TextChoices):
        RESERVED = "reserved", _("Reserved")
        OUT = "out", _("Out")
        RETURNED = "returned", _("Returned")
        LOST = "lost", _("Not returned")

    turf = models.ForeignKey(Turf, on_delete=models.PROTECT, related_name="rentals")
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rentals",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rentals",
    )
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rentals"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="rentals")
    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)]
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.RESERVED, db_index=True
    )
    price = models.DecimalField(_("rental price"), max_digits=12, decimal_places=2, default=0)
    deposit = models.DecimalField(_("deposit"), max_digits=12, decimal_places=2, default=0)
    charges = models.DecimalField(
        _("charges"),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Damage or loss, settled against the deposit.",
    )
    out_at = models.DateTimeField(_("taken out at"), null=True, blank=True)
    returned_at = models.DateTimeField(_("returned at"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("rental")
        verbose_name_plural = _("rentals")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["turf", "status"], name="rental_turf_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product.name} ({self.get_status_display()})"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
PRODUCT_OWNER_CHOICES = OwnerType.choices
PRODUCT_KIND_CHOICES = ProductKind.choices
STOCK_LOCATION_KIND_CHOICES = StockLocation.Kind.choices
STOCK_MOVEMENT_TYPE_CHOICES = MovementType.choices
COUNTER_SALE_STATUS_CHOICES = CounterSale.Status.choices
RENTAL_STATUS_CHOICES = Rental.Status.choices
