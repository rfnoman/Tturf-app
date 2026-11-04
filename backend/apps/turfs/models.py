"""Turfs, grounds, hours and pricing (DOMAIN §4).

A **turf** is the venue; a **ground** is a bookable surface inside it. Players book a
ground for a time range (Phase 03), so everything here exists to answer one question:
*which slots on which ground are open, and what do they cost?*

* `Turf` carries the venue's identity, its PostGIS `location` for "near me" search, and a
  status machine that keeps unapproved venues out of every public endpoint.
* `TurfMembership` is how ownership and staffing are modelled — roles are permissions on
  one account, never separate user types (DOMAIN §1).
* `OperatingHours` and `Closure` say when a turf is open; `PriceRule` says what a slot
  costs. A ground cannot be activated until its price rules cover every open minute,
  which is what stops Phase 03 from ever having to price a slot it cannot price.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.validators import validate_image_upload
from apps.sports.models import Sport, SportFormat


#: Monday is 0, matching Python's ``date.weekday()`` — not Django's ``__week_day``.
class Weekday(models.IntegerChoices):
    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class Amenity(BaseModel):
    """Something a turf offers: floodlights, parking, changing room, cafe (DOMAIN §4).

    A model rather than a fixed list so an admin can add one without a deploy.
    """

    key = models.SlugField(_("key"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=80)
    icon = models.CharField(_("icon"), max_length=32, blank=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("amenity")
        verbose_name_plural = _("amenities")
        ordering = ["order", "label"]

    def __str__(self) -> str:
        return self.label


class Turf(BaseModel):
    """A venue. Only ``approved`` turfs are visible or bookable (DOMAIN §4)."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING_REVIEW = "pending_review", _("Pending review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        SUSPENDED = "suspended", _("Suspended")

    #: Statuses a player may see. Everything else is invisible outside the owner's area.
    PUBLIC_STATUSES = (Status.APPROVED,)

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    description = models.TextField(_("description"), blank=True)
    address = models.TextField(_("address"))
    area = models.CharField(
        _("area"),
        max_length=80,
        db_index=True,
        help_text="Neighbourhood, e.g. Dhanmondi. Players filter and search on this.",
    )
    city = models.CharField(_("city"), max_length=80, default="Dhaka", db_index=True)
    location = gis_models.PointField(
        _("location"),
        geography=True,
        srid=4326,
        help_text=(
            "WGS84 longitude/latitude. `geography=True` so distance queries return metres "
            "on the sphere rather than degrees."
        ),
    )
    phone = models.CharField(_("contact phone"), max_length=32, blank=True)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="turfs")

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    rejection_reason = models.TextField(_("rejection reason"), blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_turfs",
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    submitted_at = models.DateTimeField(_("submitted for review at"), null=True, blank=True)

    auto_confirm_enabled = models.BooleanField(
        _("auto-confirm reliable players"),
        default=True,
        help_text=(
            "DECISIONS D3: when off, every cash booking waits for owner or staff "
            "confirmation regardless of the player's record."
        ),
    )
    cancellation_free_hours = models.PositiveSmallIntegerField(
        _("free cancellation window (hours)"),
        default=12,
        help_text="Cancelling later than this counts against the player's reliability.",
    )
    advance_percent = models.PositiveSmallIntegerField(
        _("advance (%)"),
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "DECISIONS D8: how much of the price has to be paid online before a booking "
            "is confirmed. Zero means cash at the turf, as before."
        ),
    )

    class Meta:
        verbose_name = _("turf")
        verbose_name_plural = _("turfs")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "area"], name="turf_status_area_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_public(self) -> bool:
        return self.status in self.PUBLIC_STATUSES

    @property
    def latitude(self) -> float | None:
        return self.location.y if self.location else None

    @property
    def longitude(self) -> float | None:
        return self.location.x if self.location else None


class TurfPhoto(BaseModel):
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(
        _("image"), upload_to="turfs/photos/", validators=[validate_image_upload]
    )
    caption = models.CharField(_("caption"), max_length=160, blank=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("turf photo")
        verbose_name_plural = _("turf photos")
        ordering = ["order", "created_at"]

    def __str__(self) -> str:
        return f"{self.turf.name} photo"


class TurfMembership(BaseModel):
    """Who may act for a turf, and in what capacity (DOMAIN §1).

    One account can hold several roles across several turfs; there is no separate
    "owner user" type. ``owner`` is the only role that may edit the turf itself.
    """

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MANAGER = "manager", _("Manager")
        CASHIER = "cashier", _("Cashier")

    class Status(models.TextChoices):
        INVITED = "invited", _("Invited")
        ACTIVE = "active", _("Active")
        REMOVED = "removed", _("Removed")

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="turf_memberships",
        help_text="Null while an invite is outstanding for someone with no account yet.",
    )
    invited_email = models.EmailField(_("invited email"), blank=True)
    invited_phone = models.CharField(_("invited phone"), max_length=32, blank=True)
    role = models.CharField(_("role"), max_length=10, choices=Role.choices)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.INVITED
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_turf_invites",
    )
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("turf membership")
        verbose_name_plural = _("turf memberships")
        ordering = ["turf__name", "role"]
        constraints = [
            # A user holds at most one role per turf. Partial, so several historical
            # `removed` rows for the same person can coexist with one live membership.
            models.UniqueConstraint(
                fields=["turf", "user"],
                condition=~models.Q(status="removed"),
                name="unique_live_membership_per_turf",
            ),
        ]

    def __str__(self) -> str:
        who = self.user or self.invited_email or self.invited_phone
        return f"{who} @ {self.turf.name} ({self.role})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class Ground(BaseModel):
    """A bookable surface inside a turf."""

    class Surface(models.TextChoices):
        ARTIFICIAL_TURF = "artificial_turf", _("Artificial turf")
        NATURAL_GRASS = "natural_grass", _("Natural grass")
        CONCRETE = "concrete", _("Concrete")
        WOODEN = "wooden", _("Wooden")
        SYNTHETIC = "synthetic", _("Synthetic court")
        CLAY = "clay", _("Clay")

    #: Slot lengths a ground may use (DOMAIN §4).
    SLOT_CHOICES = [(60, _("60 minutes")), (90, _("90 minutes")), (120, _("120 minutes"))]

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="grounds")
    name = models.CharField(_("name"), max_length=80)
    slug = models.SlugField(_("slug"), max_length=80)
    surface = models.CharField(
        _("surface"), max_length=20, choices=Surface.choices, default=Surface.ARTIFICIAL_TURF
    )
    sport_formats = models.ManyToManyField(
        SportFormat,
        related_name="grounds",
        help_text="Which games can be played here. Drives the match capacity in Phase 04.",
    )
    max_players = models.PositiveSmallIntegerField(
        _("maximum players"),
        validators=[MinValueValidator(2)],
        help_text="Caps match capacity even when the format would allow more.",
    )
    slot_minutes = models.PositiveSmallIntegerField(
        _("slot length (minutes)"), choices=SLOT_CHOICES, default=60
    )
    is_active = models.BooleanField(
        _("active"),
        default=False,
        help_text=(
            "Bookable. Activation is refused until price rules cover every open minute "
            "(see apps.turfs.services.activate_ground)."
        ),
    )
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("ground")
        verbose_name_plural = _("grounds")
        ordering = ["turf__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["turf", "slug"], name="unique_ground_slug_per_turf"),
        ]

    def __str__(self) -> str:
        return f"{self.turf.name} — {self.name}"

    @property
    def sports(self) -> list[Sport]:
        """Distinct sports this ground supports, in catalogue order."""
        seen: dict[str, Sport] = {}
        for fmt in self.sport_formats.select_related("sport").all():
            seen.setdefault(fmt.sport.slug, fmt.sport)
        return sorted(seen.values(), key=lambda s: (s.order, s.name))


class OperatingHours(BaseModel):
    """When a turf is open on a given weekday.

    A ``close_time`` at or before ``open_time`` means the turf closes **after midnight**
    — 18:00–02:00 is a normal Dhaka evening. Availability slicing resolves that into the
    following calendar day rather than producing an empty window.
    """

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="operating_hours")
    weekday = models.PositiveSmallIntegerField(_("weekday"), choices=Weekday.choices)
    open_time = models.TimeField(_("opens"))
    close_time = models.TimeField(_("closes"))

    class Meta:
        verbose_name = _("operating hours")
        verbose_name_plural = _("operating hours")
        ordering = ["turf__name", "weekday", "open_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["turf", "weekday", "open_time"],
                name="unique_opening_per_turf_weekday",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.turf.name} {self.get_weekday_display()} {self.open_time}–{self.close_time}"

    @property
    def crosses_midnight(self) -> bool:
        return self.close_time <= self.open_time


class Closure(BaseModel):
    """A blackout period for a whole turf or a single ground (DOMAIN §4)."""

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="closures")
    ground = models.ForeignKey(
        Ground,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="closures",
        help_text="Leave empty to close the whole turf.",
    )
    starts_at = models.DateTimeField(_("starts"))
    ends_at = models.DateTimeField(_("ends"))
    reason = models.CharField(_("reason"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("closure")
        verbose_name_plural = _("closures")
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="closure_ends_after_it_starts",
            ),
        ]
        indexes = [
            models.Index(fields=["turf", "starts_at", "ends_at"], name="closure_window_idx"),
        ]

    def __str__(self) -> str:
        target = self.ground or self.turf
        return f"{target} closed {self.starts_at:%Y-%m-%d %H:%M}"


class PriceRule(BaseModel):
    """What one slot on this ground costs, for a set of weekdays and a time window.

    The most specific matching rule wins (DOMAIN §4): fewer weekdays beats more, and a
    shorter window beats a longer one. That lets a turf keep one broad "all week" rule
    and override Friday nights without reordering anything.
    """

    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name="price_rules")
    weekdays = models.JSONField(
        _("weekdays"),
        default=list,
        help_text="Monday is 0, matching Python's date.weekday(). Empty means every day.",
    )
    start_time = models.TimeField(_("from"))
    end_time = models.TimeField(_("until"))
    price = models.DecimalField(
        _("price per slot"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="BDT. Money is always Decimal (CLAUDE.md).",
    )
    label = models.CharField(
        _("label"), max_length=40, blank=True, help_text="e.g. Peak, Off-peak, Night."
    )

    class Meta:
        verbose_name = _("price rule")
        verbose_name_plural = _("price rules")
        ordering = ["ground__name", "start_time"]

    def __str__(self) -> str:
        return f"{self.ground} {self.start_time}–{self.end_time} ৳{self.price}"

    @property
    def crosses_midnight(self) -> bool:
        return self.end_time <= self.start_time

    def covers_weekday(self, weekday: int) -> bool:
        return not self.weekdays or weekday in self.weekdays

    @property
    def specificity(self) -> tuple[int, int]:
        """Sort key: lower is more specific.

        ``(number of weekdays, window length in minutes)`` — an empty weekday list means
        all seven, so it ranks least specific.
        """
        days = len(self.weekdays) if self.weekdays else len(Weekday.values)
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        span = (end - start) if end > start else (24 * 60 - start + end)
        return (days, span)


#: Importable aliases for `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`, which resolves
#: a dotted path and so cannot reach a TextChoices nested inside a model.
TURF_STATUS_CHOICES = Turf.Status.choices
TURF_MEMBERSHIP_STATUS_CHOICES = TurfMembership.Status.choices
TURF_MEMBERSHIP_ROLE_CHOICES = TurfMembership.Role.choices
GROUND_SURFACE_CHOICES = Ground.Surface.choices
