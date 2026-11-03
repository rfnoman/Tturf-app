"""Scorecards, MOTM and peer ratings (DOMAIN §7).

A scorecard is the record of what happened, and it is what Phase 06's rating engine
consumes — so its job is to be *trustworthy*, which shapes everything here:

* **The form is generated from the sport**, not hard-coded. ``PlayerStat`` points at a
  ``StatDefinition``, so adding a stat to a sport changes the scorecard with no code.
* **It is confirmed by somebody other than the scorer.** The opposing captain confirms,
  or disputes; silence for 24 hours counts as agreement (DOMAIN §7).
* **Locking is final.** `locked` is terminal: ratings have been computed from it, and a
  number that can move under the engine's feet is worse than no number.
* **Staff verification is an upgrade, not a requirement** (DECISIONS D7) — it earns the
  scorecard a ×1.5 weight in Phase 06, and a badge players can see.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.matches.models import Match, MatchPlayer
from apps.sports.models import StatDefinition


class TeamSide(models.TextChoices):
    A = "A", _("Team A")
    B = "B", _("Team B")


class MatchTeam(BaseModel):
    """One side of a match. Two per match, created together."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="teams")
    side = models.CharField(_("side"), max_length=1, choices=TeamSide.choices)
    name = models.CharField(_("name"), max_length=60, blank=True)
    captain = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captained_teams",
        help_text="Confirms or disputes the *other* side's scorecard (DOMAIN §7).",
    )

    class Meta:
        verbose_name = _("match team")
        verbose_name_plural = _("match teams")
        ordering = ["side"]
        constraints = [
            models.UniqueConstraint(fields=["match", "side"], name="unique_side_per_match"),
        ]

    def __str__(self) -> str:
        return self.name or f"Team {self.side}"

    @property
    def display_name(self) -> str:
        return self.name or f"Team {self.side}"


class MatchTeamPlayer(BaseModel):
    """A roster entry assigned to a side.

    Points at ``MatchPlayer`` rather than the account: a player who was removed from the
    roster cannot still be on a team sheet.
    """

    team = models.ForeignKey(MatchTeam, on_delete=models.CASCADE, related_name="players")
    match_player = models.OneToOneField(
        MatchPlayer, on_delete=models.CASCADE, related_name="team_entry"
    )
    position = models.CharField(_("position"), max_length=40, blank=True)

    class Meta:
        verbose_name = _("team player")
        verbose_name_plural = _("team players")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.match_player.player} on {self.team}"

    @property
    def player(self):
        return self.match_player.player


class ScorecardStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SUBMITTED = "submitted", _("Submitted, awaiting confirmation")
    DISPUTED = "disputed", _("Disputed")
    CONFIRMED = "confirmed", _("Confirmed")
    LOCKED = "locked", _("Locked")


class MatchResult(models.TextChoices):
    TEAM_A = "A", _("Team A won")
    TEAM_B = "B", _("Team B won")
    DRAW = "draw", _("Draw")


class Scorecard(BaseModel):
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="scorecard")
    scorer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scored_matches",
        help_text="Defaults to the organiser; reassignable to a captain or turf staff.",
    )
    team_a_score = models.PositiveSmallIntegerField(_("team A"), default=0)
    team_b_score = models.PositiveSmallIntegerField(_("team B"), default=0)
    extra = models.JSONField(
        _("team stats"),
        default=dict,
        blank=True,
        help_text=(
            "Sport-specific team-scope values keyed by StatDefinition key, e.g. cricket "
            "overs and wickets per side, as {side: {stat_key: value}}."
        ),
    )
    result = models.CharField(_("result"), max_length=5, choices=MatchResult.choices, blank=True)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=ScorecardStatus.choices,
        default=ScorecardStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_scorecards",
    )
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    auto_confirmed = models.BooleanField(
        _("auto-confirmed"),
        default=False,
        help_text="Nobody acted within the window, which DOMAIN §7 counts as agreement.",
    )
    verified_by_staff = models.BooleanField(
        _("verified by the turf"),
        default=False,
        help_text="DECISIONS D7: entered or confirmed by turf staff. Weighs x1.5 in ratings.",
    )
    dispute_reason = models.CharField(_("dispute reason"), max_length=300, blank=True)
    disputed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputed_scorecards",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_scorecards",
    )
    locked_at = models.DateTimeField(_("locked at"), null=True, blank=True)
    motm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="motm_awards",
        help_text="Set when voting closes (DOMAIN §7).",
    )
    motm_closed_at = models.DateTimeField(_("voting closed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("scorecard")
        verbose_name_plural = _("scorecards")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.team_a_score}–{self.team_b_score} ({self.status})"

    @property
    def is_locked(self) -> bool:
        return self.status == ScorecardStatus.LOCKED

    @property
    def is_editable(self) -> bool:
        """Draft and disputed are the only states a scorer may write to."""
        return self.status in (ScorecardStatus.DRAFT, ScorecardStatus.DISPUTED)

    def score_for(self, side: str) -> int:
        return self.team_a_score if side == TeamSide.A else self.team_b_score


class PlayerStat(BaseModel):
    """One stat value for one player on one scorecard.

    The ``stat_definition`` FK is what makes the scorecard sport-driven: the entry form
    and the validators both read the sport's definitions, so a new stat needs no code.
    """

    scorecard = models.ForeignKey(Scorecard, on_delete=models.CASCADE, related_name="player_stats")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_stats"
    )
    stat_definition = models.ForeignKey(
        StatDefinition, on_delete=models.CASCADE, related_name="player_values"
    )
    value = models.DecimalField(_("value"), max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("player stat")
        verbose_name_plural = _("player stats")
        ordering = ["stat_definition__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["scorecard", "player", "stat_definition"],
                name="unique_stat_per_player_per_scorecard",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player} {self.stat_definition.label}={self.value}"


class ScorecardEvent(BaseModel):
    """Append-only history of the scorecard's transitions (CLAUDE.md)."""

    scorecard = models.ForeignKey(Scorecard, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(
        _("from"), max_length=10, choices=ScorecardStatus.choices, blank=True
    )
    to_status = models.CharField(_("to"), max_length=10, choices=ScorecardStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scorecard_events",
        help_text="Null when the system did it — auto-confirmation runs unattended.",
    )
    note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("scorecard event")
        verbose_name_plural = _("scorecard events")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.from_status or '—'} -> {self.to_status}"


class MotmVote(BaseModel):
    """One player's man-of-the-match vote (DOMAIN §7).

    Only roster players vote, never for themselves, and the window closes 24 hours after
    submission.
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="motm_votes")
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="motm_votes_cast"
    )
    nominee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="motm_votes_received",
    )

    class Meta:
        verbose_name = _("MOTM vote")
        verbose_name_plural = _("MOTM votes")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["match", "voter"], name="one_motm_vote_per_voter"),
            models.CheckConstraint(
                condition=~models.Q(voter=models.F("nominee")),
                name="no_self_motm_vote",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.voter} -> {self.nominee}"


class PeerRating(BaseModel):
    """One player rating another after a match (DOMAIN §7).

    **Anonymous to the recipient**: the rater is stored so a person cannot rate the same
    opponent twice, but nothing in the API ever returns who gave what.
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="peer_ratings")
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="peer_ratings_given"
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="peer_ratings_received",
    )
    overall = models.PositiveSmallIntegerField(
        _("overall"), validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    skill_taps = models.JSONField(
        _("skill taps"),
        default=list,
        blank=True,
        help_text="Optional sport-skill keys the rater singled out, e.g. finishing.",
    )

    class Meta:
        verbose_name = _("peer rating")
        verbose_name_plural = _("peer ratings")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "rater", "ratee"], name="one_peer_rating_per_pair_per_match"
            ),
            models.CheckConstraint(
                condition=~models.Q(rater=models.F("ratee")), name="no_self_peer_rating"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ratee}: {self.overall}/5"


#: Importable aliases for ENUM_NAME_OVERRIDES (see apps/turfs/models.py).
SCORECARD_STATUS_CHOICES = ScorecardStatus.choices
MATCH_RESULT_CHOICES = MatchResult.choices
TEAM_SIDE_CHOICES = TeamSide.choices
