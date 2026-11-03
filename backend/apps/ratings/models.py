"""Rating history, track record, conduct and discovery (DOMAIN §3 and §8).

The live numbers stay where Phase 01 put them — `PlayerSportRating`, `PlayerSkill`,
`PlayerAttribute`. What lives here is everything *around* them: why a rating changed,
what a player has actually done (overall and per ground), what other people reported,
who is on top of a leaderboard, and when somebody is free to play.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.players.models import PlayerProfile
from apps.sports.models import Sport
from apps.turfs.models import Ground, Turf


class RatingChange(BaseModel):
    """One locked match's effect on one player's rating, with the reasoning kept.

    Stored rather than derived: the weights are versioned, and an explanation shown on
    the profile months later has to be the explanation that was true at the time.
    """

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="rating_changes"
    )
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="rating_changes")
    match = models.ForeignKey(
        "matches.Match", on_delete=models.CASCADE, related_name="rating_changes"
    )
    inputs = models.JSONField(
        _("inputs"),
        default=dict,
        help_text=(
            "The match as the engine saw it: stats, result, MOTM, peer average and the "
            "two team averages. Stored so a replay re-runs the same match, rather than "
            "the match as it would look with today's ratings."
        ),
    )
    before_overall = models.PositiveSmallIntegerField(_("before"))
    after_overall = models.PositiveSmallIntegerField(_("after"))
    breakdown = models.JSONField(
        _("breakdown"),
        default=dict,
        help_text="The engine's explanation: components, weights, clamps and deltas.",
    )
    weights_version = models.PositiveSmallIntegerField(_("weights version"), default=1)
    played_at = models.DateTimeField(_("played at"), db_index=True)

    class Meta:
        verbose_name = _("rating change")
        verbose_name_plural = _("rating changes")
        ordering = ["-played_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "match"], name="unique_rating_change_per_match"
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "sport", "-played_at"], name="rating_change_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} {self.before_overall}→{self.after_overall}"

    @property
    def delta(self) -> int:
        return self.after_overall - self.before_overall


class StatTotals(models.Model):
    """Shared shape for the two track-record tables."""

    matches = models.PositiveIntegerField(_("matches"), default=0)
    wins = models.PositiveIntegerField(_("wins"), default=0)
    draws = models.PositiveIntegerField(_("draws"), default=0)
    losses = models.PositiveIntegerField(_("losses"), default=0)
    motm_awards = models.PositiveIntegerField(_("MOTM awards"), default=0)
    stat_totals = models.JSONField(
        _("stat totals"),
        default=dict,
        blank=True,
        help_text='{stat key: total}, e.g. {"goals": 14}. Keyed by the sport\'s own stats.',
    )

    class Meta:
        abstract = True

    @property
    def win_rate(self) -> float:
        return round(self.wins / self.matches, 3) if self.matches else 0.0


class PlayerSportStats(StatTotals, BaseModel):
    """A player's career totals in one sport, summed from locked scorecards."""

    profile = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name="sport_stats")
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="player_stats_totals")
    #: Most recent first, capped — the form guide (DOMAIN §3: "form (last 5)").
    recent_results = models.JSONField(_("recent results"), default=list, blank=True)

    class Meta:
        verbose_name = _("player sport stats")
        verbose_name_plural = _("player sport stats")
        ordering = ["sport__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "sport"], name="unique_sport_stats_per_player"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} / {self.sport.name}"


class PlayerGroundStats(StatTotals, BaseModel):
    """The same totals, per ground — "3× MOTM at Mirpur" (DOMAIN §8)."""

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="ground_stats"
    )
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="player_stats")
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name="player_stats")
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="ground_player_stats")

    class Meta:
        verbose_name = _("player ground stats")
        verbose_name_plural = _("player ground stats")
        ordering = ["-matches"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "ground", "sport"], name="unique_ground_stats_per_player"
            ),
        ]
        indexes = [
            models.Index(fields=["turf", "sport", "-matches"], name="ground_stats_turf_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} at {self.ground.name}"


class ConductReport(BaseModel):
    """One player reporting another for what happened in a match (DOMAIN §8).

    Nothing a report says affects a rating until an admin upholds it: an accusation is
    not evidence, and a fair-play score that anyone can move by complaining is worthless.
    """

    class Reason(models.TextChoices):
        ABUSIVE = "abusive", _("Abusive behaviour")
        LEFT_EARLY = "left_early", _("Left the match early")
        NO_SHOW = "no_show", _("Did not turn up")
        UNSAFE_PLAY = "unsafe_play", _("Unsafe play")
        OTHER = "other", _("Something else")

    class Status(models.TextChoices):
        OPEN = "open", _("Awaiting review")
        UPHELD = "upheld", _("Upheld")
        DISMISSED = "dismissed", _("Dismissed")

    match = models.ForeignKey(
        "matches.Match", on_delete=models.CASCADE, related_name="conduct_reports"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conduct_reports_made"
    )
    reported = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conduct_reports_received",
    )
    reason = models.CharField(_("reason"), max_length=16, choices=Reason.choices)
    details = models.TextField(_("details"), max_length=1000, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conduct_reports_reviewed",
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    review_note = models.CharField(_("review note"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("conduct report")
        verbose_name_plural = _("conduct reports")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "reporter", "reported"], name="one_report_per_person_per_match"
            ),
            models.CheckConstraint(
                condition=~models.Q(reporter=models.F("reported")),
                name="no_self_conduct_report",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reported} — {self.get_reason_display()}"


class Availability(BaseModel):
    """ "Free on Friday evening in Mirpur" (DOMAIN §3)."""

    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="availability"
    )
    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="availability",
        null=True,
        blank=True,
        help_text="Null means any sport they play.",
    )
    starts_at = models.DateTimeField(_("from"))
    ends_at = models.DateTimeField(_("until"))
    area = models.CharField(_("area"), max_length=120, blank=True)
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("availability")
        verbose_name_plural = _("availability")
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="availability_ends_after_it_starts",
            ),
        ]
        indexes = [
            models.Index(fields=["starts_at", "ends_at"], name="availability_window_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.profile.name} free {self.starts_at:%d %b %H:%M}"


class LeaderboardEntry(BaseModel):
    """A row of a computed leaderboard (DOMAIN §8).

    Written nightly by a Celery task rather than computed per request: these are read on
    every turf page and change once a day at most.
    """

    class Metric(models.TextChoices):
        RATING = "rating", _("Highest rated")
        MOTM = "motm", _("Most MOTM awards")
        WINS = "wins", _("Most wins")
        RELIABILITY = "reliability", _("Most reliable")
        TOP_STAT = "top_stat", _("Top of a sport stat")

    class Period(models.TextChoices):
        MONTH = "month", _("This month")
        ALL_TIME = "all_time", _("All time")

    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="leaderboard_entries")
    turf = models.ForeignKey(
        Turf,
        on_delete=models.CASCADE,
        related_name="leaderboard_entries",
        null=True,
        blank=True,
        help_text="Null for the platform-wide board.",
    )
    metric = models.CharField(_("metric"), max_length=12, choices=Metric.choices)
    stat_key = models.CharField(
        _("stat"), max_length=40, blank=True, help_text='Only for metric="top_stat", e.g. "goals".'
    )
    period = models.CharField(_("period"), max_length=10, choices=Period.choices)
    period_start = models.DateField(_("period start"))
    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.CASCADE, related_name="leaderboard_entries"
    )
    rank = models.PositiveSmallIntegerField(_("rank"), validators=[MinValueValidator(1)])
    value = models.DecimalField(_("value"), max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = _("leaderboard entry")
        verbose_name_plural = _("leaderboard entries")
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["sport", "turf", "metric", "stat_key", "period", "period_start", "profile"],
                name="unique_leaderboard_row",
            ),
        ]
        indexes = [
            models.Index(
                fields=["turf", "sport", "metric", "period", "rank"], name="leaderboard_read_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.rank} {self.profile.name} ({self.get_metric_display()})"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
CONDUCT_REPORT_REASON_CHOICES = ConductReport.Reason.choices
CONDUCT_REPORT_STATUS_CHOICES = ConductReport.Status.choices
LEADERBOARD_METRIC_CHOICES = LeaderboardEntry.Metric.choices
LEADERBOARD_PERIOD_CHOICES = LeaderboardEntry.Period.choices
