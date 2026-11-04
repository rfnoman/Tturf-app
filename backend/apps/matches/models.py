"""Squads, matches and how players get into them (DOMAIN §6).

Every booking creates exactly one ``Match``; the **roster lives on the match**, not on
the booking, because a booking is a commercial fact (who pays for the ground) while a
match is a sporting one (who plays). They diverge immediately: the booker may not play,
and nine other people may.

How a player gets in depends on the match's visibility, which DOMAIN §6 derives from the
booking and the squad:

| Booking            | Visibility | Who can get in                                  |
|--------------------|------------|-------------------------------------------------|
| individual, public | board      | anyone requests -> booker approves               |
| individual, private| hidden     | booker invites                                   |
| group, open        | board      | anyone requests -> leader approves               |
| group, closed      | squad only | member proposes -> leader approves -> player accepts |

That last chain is DECISIONS D1, and it is why ``MatchInvite`` has a ``proposed`` state
that an invite from the leader skips.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.validators import validate_image_upload
from apps.players.models import PlayerProfile
from apps.sports.models import Sport, SportFormat


class Squad(BaseModel):
    """A persistent group that books and plays together (DOMAIN §6)."""

    name = models.CharField(_("name"), max_length=80)
    slug = models.SlugField(_("slug"), max_length=90, unique=True)
    description = models.TextField(_("description"), max_length=500, blank=True)
    crest = models.ImageField(
        _("crest"),
        upload_to="squads/crests/",
        blank=True,
        null=True,
        validators=[validate_image_upload],
    )
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="led_squads"
    )
    sports = models.ManyToManyField(Sport, blank=True, related_name="squads")
    area = models.CharField(_("area"), max_length=80, blank=True, db_index=True)
    accepts_public_requests = models.BooleanField(
        _("open squad"),
        default=False,
        help_text=(
            "Open: squad matches reach the match board and anyone may request to join. "
            "Closed: squad only, and members propose players for the leader to approve."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_squads",
    )

    class Meta:
        verbose_name = _("squad")
        verbose_name_plural = _("squads")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def member_count(self) -> int:
        return self.memberships.filter(status=SquadMembership.Status.ACTIVE).count()


class SquadMembership(BaseModel):
    class Role(models.TextChoices):
        LEADER = "leader", _("Leader")
        MEMBER = "member", _("Member")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        LEFT = "left", _("Left")
        REMOVED = "removed", _("Removed")

    squad = models.ForeignKey(Squad, on_delete=models.CASCADE, related_name="memberships")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="squad_memberships"
    )
    role = models.CharField(_("role"), max_length=8, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(
        _("status"), max_length=8, choices=Status.choices, default=Status.ACTIVE
    )
    joined_at = models.DateTimeField(_("joined at"), null=True, blank=True)

    class Meta:
        verbose_name = _("squad membership")
        verbose_name_plural = _("squad memberships")
        ordering = ["role", "joined_at"]
        constraints = [
            # Partial, so leaving and rejoining does not collide with the old row.
            models.UniqueConstraint(
                fields=["squad", "player"],
                condition=models.Q(status="active"),
                name="unique_active_squad_membership",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player} in {self.squad} ({self.role})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class SquadInvite(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        CANCELLED = "cancelled", _("Cancelled")

    squad = models.ForeignKey(Squad, on_delete=models.CASCADE, related_name="invites")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="squad_invites"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_squad_invites",
    )
    message = models.CharField(_("message"), max_length=300, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    class Meta:
        verbose_name = _("squad invitation")
        verbose_name_plural = _("squad invitations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["squad", "player"],
                condition=models.Q(status="pending"),
                name="unique_pending_squad_invite",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.squad} -> {self.player} ({self.status})"


class MatchVisibility(models.TextChoices):
    """Derived from the booking and the squad — never set by hand (DOMAIN §6)."""

    BOARD = "board", _("On the match board")
    PRIVATE = "private", _("Invite only")
    SQUAD = "squad", _("Squad only")


class MatchStatus(models.TextChoices):
    UPCOMING = "upcoming", _("Upcoming")
    IN_PROGRESS = "in_progress", _("In progress")
    FINISHED = "finished", _("Finished")
    CANCELLED = "cancelled", _("Cancelled")


class Match(BaseModel):
    """The game itself. Exactly one per booking (DOMAIN §6)."""

    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.CASCADE, related_name="match"
    )
    squad = models.ForeignKey(
        Squad,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches",
        help_text="Set for a group booking.",
    )
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="matches")
    sport_format = models.ForeignKey(SportFormat, on_delete=models.PROTECT, related_name="matches")
    capacity = models.PositiveSmallIntegerField(
        _("capacity"),
        validators=[MinValueValidator(2)],
        help_text=(
            "players_per_side x 2, capped by the ground's max_players — a 7v7 format on "
            "a ground that holds 10 is a 10-player match."
        ),
    )
    visibility = models.CharField(
        _("visibility"), max_length=8, choices=MatchVisibility.choices, db_index=True
    )
    status = models.CharField(
        _("status"),
        max_length=12,
        choices=MatchStatus.choices,
        default=MatchStatus.UPCOMING,
        db_index=True,
    )
    notes = models.TextField(_("notes"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("match")
        verbose_name_plural = _("matches")
        ordering = ["booking__time_range"]
        indexes = [
            models.Index(fields=["visibility", "status"], name="match_board_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.sport.name} at {self.booking.ground} ({self.status})"

    # Delegating rather than duplicating: the booking owns when and where, and a copy
    # would drift the first time a booking is rescheduled.
    @property
    def starts_at(self):
        return self.booking.starts_at

    @property
    def ends_at(self):
        return self.booking.ends_at

    @property
    def ground(self):
        return self.booking.ground

    @property
    def turf(self):
        return self.booking.ground.turf

    @property
    def organiser(self):
        """Who decides who gets in: the squad leader, or the booker (DOMAIN §6)."""
        return self.squad.leader if self.squad_id else self.booking.booked_by

    @property
    def roster_count(self) -> int:
        return self.players.count()

    @property
    def needed(self) -> int:
        return max(0, self.capacity - self.roster_count)

    @property
    def is_full(self) -> bool:
        return self.needed == 0

    @property
    def is_open_for_joining(self) -> bool:
        return self.status == MatchStatus.UPCOMING and not self.is_full


class MatchPlayer(BaseModel):
    """One player on the roster."""

    class Source(models.TextChoices):
        BOOKER = "booker", _("Booked the ground")
        SQUAD = "squad", _("Squad member")
        REQUEST = "request", _("Asked to join")
        INVITE = "invite", _("Invited")
        STAFF = "staff", _("Added by turf staff")

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_entries"
    )
    source = models.CharField(_("how they joined"), max_length=8, choices=Source.choices)
    attended = models.BooleanField(
        _("attended"),
        null=True,
        blank=True,
        help_text="Filled in from the Phase 05 scorecard; null until the match is played.",
    )

    class Meta:
        verbose_name = _("match player")
        verbose_name_plural = _("match players")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["match", "player"], name="unique_player_per_match"),
        ]

    def __str__(self) -> str:
        return f"{self.player} in {self.match}"

    @property
    def profile(self) -> PlayerProfile | None:
        return getattr(self.player, "player_profile", None)


class JoinRequest(BaseModel):
    """A player asking to join a match they found (DOMAIN §6)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        DECLINED = "declined", _("Declined")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        EXPIRED = "expired", _("Expired")

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="join_requests")
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="join_requests"
    )
    message = models.CharField(_("message"), max_length=300, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_join_requests",
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)
    decision_note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("join request")
        verbose_name_plural = _("join requests")
        ordering = ["created_at"]
        constraints = [
            # One live ask per player per match; a declined one can be followed by
            # another if the organiser changes their mind.
            models.UniqueConstraint(
                fields=["match", "player"],
                condition=models.Q(status="pending"),
                name="unique_pending_join_request",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player} -> {self.match} ({self.status})"


class MatchInvite(BaseModel):
    """An invitation to play, including the closed-squad chain (DECISIONS D1).

    ``proposed`` exists only for a closed squad: a member suggests somebody, the leader
    approves, and only then does the player see it. An invite from the leader or the
    booker starts at ``leader_approved``, because there is nobody left to ask.
    """

    class Status(models.TextChoices):
        PROPOSED = "proposed", _("Proposed, awaiting the leader")
        LEADER_APPROVED = "leader_approved", _("Awaiting the player")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        REJECTED = "rejected", _("Rejected by the leader")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="invites")
    invited_player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_invites"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_match_invites",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_match_invites",
    )
    message = models.CharField(_("message"), max_length=300, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.PROPOSED
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    class Meta:
        verbose_name = _("match invitation")
        verbose_name_plural = _("match invitations")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "invited_player"],
                condition=models.Q(status__in=["proposed", "leader_approved"]),
                name="unique_live_match_invite",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.match} invites {self.invited_player} ({self.status})"

    @property
    def is_live(self) -> bool:
        return self.status in (self.Status.PROPOSED, self.Status.LEADER_APPROVED)


#: Importable aliases for `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`, which resolves a
#: dotted path and so cannot reach a TextChoices nested inside a model.
JOIN_REQUEST_STATUS_CHOICES = JoinRequest.Status.choices
MATCH_INVITE_STATUS_CHOICES = MatchInvite.Status.choices
SQUAD_INVITE_STATUS_CHOICES = SquadInvite.Status.choices
SQUAD_ROLE_CHOICES = SquadMembership.Role.choices
SQUAD_MEMBERSHIP_STATUS_CHOICES = SquadMembership.Status.choices
MATCH_PLAYER_SOURCE_CHOICES = MatchPlayer.Source.choices
