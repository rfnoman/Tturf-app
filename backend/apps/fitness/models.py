"""The fitness layer (DOMAIN §10).

A match is already a workout; this app is what makes the app say so. Every locked
scorecard — and every completed booking that never got one — becomes an `ActivityLog`,
and from those come the week's totals, the streak and the goals.

Nothing here invents numbers it cannot justify: a calorie figure built on a guessed body
weight is flagged as an estimate, and the UI says so.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.inventory.models import Product
from apps.sports.models import Sport
from apps.turfs.models import Turf


class ActivitySource(models.TextChoices):
    MATCH = "match", _("A match")
    MANUAL = "manual", _("Added by the player")


class ActivityLog(BaseModel):
    """One session of doing something, logged once."""

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity"
    )
    sport = models.ForeignKey(
        Sport,
        on_delete=models.PROTECT,
        related_name="activity",
        null=True,
        blank=True,
        help_text="Null for a gym session or a run the player typed in.",
    )
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity",
    )
    source = models.CharField(
        _("source"), max_length=8, choices=ActivitySource.choices, default=ActivitySource.MATCH
    )
    #: Dhaka-local date. Stored as a date because "which day did I play?" is a local
    #: question, and a UTC timestamp answers it wrong either side of midnight.
    happened_on = models.DateField(_("date"), db_index=True)
    minutes = models.PositiveIntegerField(_("minutes"), validators=[MinValueValidator(1)])
    est_calories = models.PositiveIntegerField(_("calories"), default=0)
    is_estimate = models.BooleanField(
        _("estimated"),
        default=False,
        help_text="True when the player's weight was unknown and the fallback was used.",
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("activity")
        verbose_name_plural = _("activity")
        ordering = ["-happened_on", "-created_at"]
        constraints = [
            # One log per player per match: the hook can fire twice and a player's week
            # must not double because a task was retried.
            models.UniqueConstraint(
                fields=["player", "match"],
                name="one_activity_per_match",
                condition=models.Q(match__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["player", "-happened_on"], name="activity_player_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.minutes} min on {self.happened_on}"


class GoalType(models.TextChoices):
    MATCHES = "matches_per_week", _("Matches a week")
    MINUTES = "minutes_per_week", _("Minutes a week")
    CALORIES = "calories_per_week", _("Calories a week")


class FitnessGoal(BaseModel):
    """What the player is aiming at this week."""

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fitness_goals"
    )
    type = models.CharField(_("type"), max_length=20, choices=GoalType.choices)
    target = models.PositiveIntegerField(_("target"), validators=[MinValueValidator(1)])
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("fitness goal")
        verbose_name_plural = _("fitness goals")
        ordering = ["type"]
        constraints = [
            models.UniqueConstraint(
                fields=["player", "type"],
                name="one_active_goal_per_type",
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()}: {self.target}"


class Occasion(models.TextChoices):
    PRE_MATCH = "pre_match", _("Before the match")
    DURING = "during", _("During the match")
    RECOVERY = "recovery", _("After the match")


class Bundle(BaseModel):
    """A curated set of products — "Evening football kit" (DOMAIN §10).

    Owned by the platform or by one turf, exactly like a product: a bundle can only be
    bought if its items are all at the same source, so the Phase 08 rule that one order
    has one source still holds.
    """

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    description = models.TextField(_("description"), max_length=500, blank=True)
    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name="bundles",
        null=True,
        blank=True,
        help_text="Null for a platform bundle.",
    )
    sport = models.ForeignKey(
        Sport, on_delete=models.SET_NULL, null=True, blank=True, related_name="bundles"
    )
    occasion = models.CharField(
        _("occasion"), max_length=10, choices=Occasion.choices, default=Occasion.PRE_MATCH
    )
    image_url = models.URLField(_("image"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("bundle")
        verbose_name_plural = _("bundles")
        ordering = ["occasion", "name"]

    def __str__(self) -> str:
        return self.name


class BundleItem(BaseModel):
    """A product in a bundle, with how many of it."""

    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="bundle_items")
    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = _("bundle item")
        verbose_name_plural = _("bundle items")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["bundle", "product"], name="unique_product_per_bundle"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product.name}"


class ReminderPreference(BaseModel):
    """What a player wants to be told, and when not to be told anything.

    One row per player, created on first read. Defaults are **on**, because the reminders
    are about a match they have already committed to — but quiet hours default to
    overnight, so nothing wakes anybody up.
    """

    player = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminder_preference"
    )
    match_day = models.BooleanField(_("match-day summary"), default=True)
    hydration = models.BooleanField(_("hydration before a match"), default=True)
    recovery = models.BooleanField(_("recovery after a match"), default=True)
    order_cutoff = models.BooleanField(_("order cutoff"), default=True)
    weekly_recap = models.BooleanField(_("weekly recap"), default=True)
    push_enabled = models.BooleanField(_("web push"), default=False)

    quiet_from = models.TimeField(
        _("quiet from"), null=True, blank=True, help_text="Dhaka time. Default 22:00."
    )
    quiet_until = models.TimeField(_("quiet until"), null=True, blank=True)

    class Meta:
        verbose_name = _("reminder preference")
        verbose_name_plural = _("reminder preferences")

    def __str__(self) -> str:
        return f"Reminders for {self.player}"

    def wants(self, kind: str) -> bool:
        """Does this player want this kind of reminder?"""
        return bool(getattr(self, kind, False))


class PushSubscription(BaseModel):
    """One browser that agreed to receive push.

    A player can have several — phone and laptop — and a dead one is deleted the first
    time the push service says it is gone.
    """

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(_("endpoint"), max_length=500, unique=True)
    p256dh = models.CharField(_("p256dh key"), max_length=200)
    auth = models.CharField(_("auth secret"), max_length=100)
    user_agent = models.CharField(_("user agent"), max_length=200, blank=True)
    last_used_at = models.DateTimeField(_("last used"), null=True, blank=True)

    class Meta:
        verbose_name = _("push subscription")
        verbose_name_plural = _("push subscriptions")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.player} ({self.endpoint[:40]}…)"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
ACTIVITY_SOURCE_CHOICES = ActivitySource.choices
FITNESS_GOAL_TYPE_CHOICES = GoalType.choices
BUNDLE_OCCASION_CHOICES = Occasion.choices
