"""The sports catalogue (DOMAIN §2).

The catalogue is global and admin-curated: owners *propose* a sport and an admin either
approves it (which creates the ``Sport``) or merges the proposal into an existing one, so
the catalogue never grows duplicates.

A ``Sport`` is the hub for everything later phases need to know about a game:

* ``SportFormat`` — 5v5, nets, doubles… each with ``players_per_side``, which Phase 04
  turns into ``Match.capacity``.
* ``SportSkill`` — sport-specific skills (finishing, bowling) that a player is rated on.
* ``SportAttributeWeight`` — how much each shared ``Attribute`` (stamina, agility, speed,
  strength) counts toward this sport's overall rating.
* ``StatDefinition`` — the fields a Phase 05 scorecard collects.
* ``met_value`` — the metabolic equivalent used for Phase 09 calorie estimates.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Attribute(BaseModel):
    """A physical attribute shared across every sport (DOMAIN §3).

    Attributes belong to the *player*, not to a sport, and therefore display on every
    sport card. Only the weighting differs per sport.
    """

    key = models.SlugField(_("key"), max_length=32, unique=True)
    label = models.CharField(_("label"), max_length=64)
    description = models.CharField(_("description"), max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("attribute")
        verbose_name_plural = _("attributes")
        ordering = ["order", "key"]

    def __str__(self) -> str:
        return self.label


class Sport(BaseModel):
    name = models.CharField(_("name"), max_length=80, unique=True)
    slug = models.SlugField(_("slug"), max_length=80, unique=True)
    description = models.TextField(_("description"), blank=True)
    icon = models.CharField(
        _("icon"),
        max_length=32,
        blank=True,
        help_text="Short emoji or icon key the frontend maps to an illustration.",
    )
    met_value = models.DecimalField(
        _("MET value"),
        max_digits=4,
        decimal_places=2,
        default=7,
        validators=[MinValueValidator(0)],
        help_text="Metabolic equivalent of task; calories = MET x weight_kg x hours.",
    )
    positions = models.JSONField(
        _("positions"),
        default=list,
        blank=True,
        help_text=(
            'Selectable positions/roles for this sport, e.g. ["GK", "DEF", "MID", "FWD"]. '
            "Offered in onboarding and shown on the profile card."
        ),
    )
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("sport")
        verbose_name_plural = _("sports")
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class SportFormat(BaseModel):
    """A way of playing a sport, e.g. football 5v5 or cricket nets."""

    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="formats")
    name = models.CharField(_("name"), max_length=60)
    slug = models.SlugField(_("slug"), max_length=60)
    players_per_side = models.PositiveSmallIntegerField(
        _("players per side"),
        validators=[MinValueValidator(1)],
        help_text="Match capacity is players_per_side x 2 unless the ground caps it lower.",
    )
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("sport format")
        verbose_name_plural = _("sport formats")
        ordering = ["sport__order", "order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["sport", "slug"], name="unique_format_slug_per_sport"),
        ]

    def __str__(self) -> str:
        return f"{self.sport.name} {self.name}"

    @property
    def capacity(self) -> int:
        return self.players_per_side * 2


class SportAttributeWeight(BaseModel):
    """How much a shared attribute counts toward this sport's overall rating."""

    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="attribute_weights")
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="sport_weights")
    weight = models.DecimalField(
        _("weight"),
        max_digits=4,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(0)],
        help_text="Relative weight; the rating engine normalises across the sport's set.",
    )

    class Meta:
        verbose_name = _("sport attribute weight")
        verbose_name_plural = _("sport attribute weights")
        ordering = ["sport__order", "attribute__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["sport", "attribute"], name="unique_attribute_weight_per_sport"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sport.name} / {self.attribute.label} = {self.weight}"


class SportSkill(BaseModel):
    """A sport-specific skill a player is rated on, e.g. finishing or bowling."""

    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="skills")
    key = models.SlugField(_("key"), max_length=40)
    label = models.CharField(_("label"), max_length=64)
    description = models.CharField(_("description"), max_length=200, blank=True)
    weight = models.DecimalField(
        _("weight"),
        max_digits=4,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(0)],
    )
    # Keeper/bowler-style skills are irrelevant to most players and would drag an
    # outfielder's overall down, so they are excluded from the headline number.
    counts_toward_overall = models.BooleanField(_("counts toward overall"), default=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("sport skill")
        verbose_name_plural = _("sport skills")
        ordering = ["sport__order", "order", "key"]
        constraints = [
            models.UniqueConstraint(fields=["sport", "key"], name="unique_skill_key_per_sport"),
        ]

    def __str__(self) -> str:
        return f"{self.sport.name} / {self.label}"


class StatDefinition(BaseModel):
    """One field on a scorecard for this sport (DOMAIN §7).

    Phase 05 renders a scorecard straight from these rows, so adding a stat to a sport
    never needs a code change.
    """

    class ValueType(models.TextChoices):
        INT = "int", _("Whole number")
        BOOL = "bool", _("Yes/no")
        DECIMAL = "decimal", _("Decimal")

    class Scope(models.TextChoices):
        PLAYER = "player", _("Per player")
        TEAM = "team", _("Per team")

    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="stat_definitions")
    key = models.SlugField(_("key"), max_length=40)
    label = models.CharField(_("label"), max_length=64)
    value_type = models.CharField(
        _("type"), max_length=10, choices=ValueType.choices, default=ValueType.INT
    )
    scope = models.CharField(_("scope"), max_length=10, choices=Scope.choices, default=Scope.PLAYER)
    min_value = models.DecimalField(_("minimum"), max_digits=8, decimal_places=2, default=0)
    max_value = models.DecimalField(
        _("maximum"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    unit = models.CharField(_("unit"), max_length=20, blank=True)
    # Phase 06 reads this: goals improve a rating, yellow cards do not.
    is_positive = models.BooleanField(
        _("positive stat"),
        default=True,
        help_text="False for cards, runs conceded and other stats you want fewer of.",
    )
    show_on_profile = models.BooleanField(_("show on profile card"), default=True)
    order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("stat definition")
        verbose_name_plural = _("stat definitions")
        ordering = ["sport__order", "order", "key"]
        constraints = [
            models.UniqueConstraint(fields=["sport", "key"], name="unique_stat_key_per_sport"),
        ]

    def __str__(self) -> str:
        return f"{self.sport.name} / {self.label}"


class SportProposal(BaseModel):
    """An owner's request for a sport the catalogue does not have yet (DOMAIN §2).

    State machine, one service function per transition (``apps/sports/services.py``):

        pending -> approved   creates a Sport
        pending -> merged     points at an existing Sport instead
        pending -> rejected   with a reason
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending review")
        APPROVED = "approved", _("Approved")
        MERGED = "merged", _("Merged into an existing sport")
        REJECTED = "rejected", _("Rejected")

    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sport_proposals",
    )
    name = models.CharField(_("proposed name"), max_length=80)
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    merged_into = models.ForeignKey(
        Sport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_proposals",
        help_text="Set when the proposal is approved (the new sport) or merged (the existing one).",
    )
    review_note = models.TextField(_("review note"), blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_sport_proposals",
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("sport proposal")
        verbose_name_plural = _("sport proposals")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.PENDING


#: Importable alias for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
SPORT_PROPOSAL_STATUS_CHOICES = SportProposal.Status.choices
STAT_VALUE_TYPE_CHOICES = StatDefinition.ValueType.choices
STAT_SCOPE_CHOICES = StatDefinition.Scope.choices
