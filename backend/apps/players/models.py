"""The player profile (DOMAIN §3).

A ``User`` is the account; a ``PlayerProfile`` is what the game knows about them. Split
in two because ``User`` mirrors Clerk and is rewritten by the webhook on every change,
while the profile is ours and must not be clobbered by a sync.

Shape of a profile:

* ``PlayerSport`` — one row per sport the player has picked up, carrying positions and
  the self-assessment they gave at onboarding. ``is_verified`` flips when they finish a
  locked match of that sport (Phase 05).
* ``PlayerAttribute`` — the four shared attributes, which display on every sport card.
* ``PlayerSkill`` — one row per sport skill, scoped to a sport through the skill itself.
* ``PlayerSportRating`` — the headline overall per sport, plus the track-record counters
  the profile card and Phase 06 leaderboards read.

Every rated value carries a ``source``: ``self`` until matches have been played,
``computed`` once the Phase 06 engine owns it. Self-assessed values are capped at
``SELF_ASSESSED_RATING_CAP`` so an unverified player cannot claim 99.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.sports.models import Attribute, Sport, SportSkill

RATING_MIN = 1
RATING_MAX = 99


class RatingSource(models.TextChoices):
    SELF = "self", _("Self-assessed")
    COMPUTED = "computed", _("Computed from matches")


def rating_validators():
    """1–99, the FIFA-style scale used for attributes, skills and overalls."""
    return [MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]


class PlayerProfile(BaseModel):
    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        OTHER = "other", _("Other")
        UNDISCLOSED = "undisclosed", _("Prefer not to say")

    class PreferredSide(models.TextChoices):
        LEFT = "left", _("Left")
        RIGHT = "right", _("Right")
        BOTH = "both", _("Both")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="player_profile"
    )
    display_name = models.CharField(
        _("display name"),
        max_length=80,
        blank=True,
        help_text="Shown on the match board and scorecards. Defaults to the Clerk name.",
    )
    photo = models.ImageField(
        _("photo"),
        upload_to="players/photos/",
        blank=True,
        null=True,
        help_text="Overrides the Clerk avatar when set.",
    )
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(_("gender"), max_length=12, choices=Gender.choices, blank=True)
    height_cm = models.PositiveSmallIntegerField(
        _("height (cm)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(80), MaxValueValidator(260)],
    )
    weight_kg = models.DecimalField(
        _("weight (kg)"),
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(300)],
        help_text=(
            "Only used for calorie estimates (DOMAIN §10). Optional; a default of "
            "DEFAULT_PLAYER_WEIGHT_KG is used and the estimate flagged when it is unset."
        ),
    )
    area = models.CharField(
        _("area"),
        max_length=80,
        blank=True,
        db_index=True,
        help_text="Neighbourhood, e.g. Dhanmondi. Used to suggest nearby turfs and matches.",
    )
    preferred_side = models.CharField(
        _("preferred foot / hand"),
        max_length=8,
        choices=PreferredSide.choices,
        blank=True,
    )
    bio = models.TextField(_("bio"), max_length=500, blank=True)
    discoverable = models.BooleanField(
        _("discoverable"),
        default=True,
        help_text="Appear in player search. A direct profile link still works (DOMAIN §3).",
    )
    reliability_score = models.PositiveSmallIntegerField(
        _("reliability"),
        default=settings.RELIABILITY_STARTING_SCORE,
        validators=[MaxValueValidator(100)],
        help_text="0–100. Drops on no-shows and late cancels, recovers on completed matches.",
    )
    onboarding_completed = models.BooleanField(_("onboarding completed"), default=False)
    onboarding_completed_at = models.DateTimeField(
        _("onboarding completed at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("player profile")
        verbose_name_plural = _("player profiles")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        """What to call this player anywhere in the UI."""
        return self.display_name or self.user.full_name or self.user.email or "Player"

    @property
    def photo_url(self) -> str:
        """Uploaded photo if there is one, otherwise the Clerk avatar."""
        if self.photo:
            return self.photo.url
        return self.user.image_url

    @property
    def effective_weight_kg(self):
        """Weight for calorie maths, falling back to the configured default."""
        return self.weight_kg or settings.DEFAULT_PLAYER_WEIGHT_KG

    @property
    def weight_is_estimated(self) -> bool:
        return self.weight_kg is None


class PlayerSport(BaseModel):
    """A sport this player plays, with the positions they fill.

    Removing a sport that has match history only hides it — the history stays
    (DOMAIN §3 / phase 01 rules), which is what ``is_hidden`` is for.
    """

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="player_sports"
    )
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="player_sports")
    positions = models.JSONField(
        _("positions"),
        default=list,
        blank=True,
        help_text='Subset of the sport\'s positions, e.g. ["MID", "FWD"].',
    )
    is_verified = models.BooleanField(
        _("verified"),
        default=False,
        help_text="True once the player has completed a locked match of this sport.",
    )
    self_assessed = models.JSONField(
        _("self-assessment"),
        default=dict,
        blank=True,
        help_text="Raw onboarding answers, kept for auditing what the player claimed.",
    )
    is_hidden = models.BooleanField(
        _("hidden"),
        default=False,
        help_text="Player removed this sport. History is kept; the card is not shown.",
    )

    class Meta:
        verbose_name = _("player sport")
        verbose_name_plural = _("player sports")
        ordering = ["sport__order", "sport__name"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "sport"], name="unique_sport_per_player"),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} / {self.sport.name}"


class PlayerAttribute(BaseModel):
    """One shared attribute value for a player, on the 1–99 scale."""

    profile = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="attributes")
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="values")
    value = models.PositiveSmallIntegerField(_("value"), validators=rating_validators())
    source = models.CharField(
        _("source"), max_length=10, choices=RatingSource.choices, default=RatingSource.SELF
    )

    class Meta:
        verbose_name = _("player attribute")
        verbose_name_plural = _("player attributes")
        ordering = ["attribute__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "attribute"], name="unique_attribute_per_player"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} / {self.attribute.label} = {self.value}"


class PlayerSkill(BaseModel):
    """One sport-specific skill value for a player."""

    profile = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="skills")
    sport_skill = models.ForeignKey(
        SportSkill, on_delete=models.CASCADE, related_name="player_values"
    )
    value = models.PositiveSmallIntegerField(_("value"), validators=rating_validators())
    source = models.CharField(
        _("source"), max_length=10, choices=RatingSource.choices, default=RatingSource.SELF
    )

    class Meta:
        verbose_name = _("player skill")
        verbose_name_plural = _("player skills")
        ordering = ["sport_skill__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "sport_skill"], name="unique_skill_per_player"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} / {self.sport_skill.label} = {self.value}"


class PlayerSportRating(BaseModel):
    """The headline overall per (player, sport), plus track-record counters.

    Phase 01 computes ``overall`` from the self-assessment with a simple weighted mean;
    Phase 06 replaces that with ``apps/ratings/engine.py`` and starts filling the
    counters from locked scorecards. The columns exist now so the profile card and the
    match board can be built against their final shape.
    """

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="sport_ratings"
    )
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="player_ratings")
    overall = models.PositiveSmallIntegerField(_("overall"), validators=rating_validators())
    is_provisional = models.BooleanField(
        _("provisional"),
        default=True,
        help_text=(
            "True until RATING_PROVISIONAL_MATCHES locked matches are counted; shown as "
            "“Unverified” on the card."
        ),
    )
    matches_counted = models.PositiveIntegerField(_("matches counted"), default=0)
    matches_played = models.PositiveIntegerField(_("matches played"), default=0)
    wins = models.PositiveIntegerField(_("wins"), default=0)
    draws = models.PositiveIntegerField(_("draws"), default=0)
    losses = models.PositiveIntegerField(_("losses"), default=0)
    motm_awards = models.PositiveIntegerField(_("man of the match awards"), default=0)
    last_match_at = models.DateTimeField(_("last match"), null=True, blank=True)

    class Meta:
        verbose_name = _("player sport rating")
        verbose_name_plural = _("player sport ratings")
        ordering = ["-overall"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "sport"], name="unique_rating_per_player_sport"
            ),
        ]
        indexes = [
            models.Index(fields=["sport", "-overall"], name="rating_sport_overall_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} / {self.sport.name} = {self.overall}"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
PLAYER_GENDER_CHOICES = PlayerProfile.Gender.choices
PLAYER_PREFERRED_SIDE_CHOICES = PlayerProfile.PreferredSide.choices
