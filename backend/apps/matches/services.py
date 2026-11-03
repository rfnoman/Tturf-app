"""Match, squad and roster business logic (DOMAIN §6, DECISIONS D1 and D2).

Two rules shape nearly everything here:

* **Capacity is decided under a row lock.** Two approvals for the last spot must not both
  succeed, so every path that adds a player re-reads the match with
  ``select_for_update()`` and counts the roster inside that lock.
* **Who may act is derived, never stored.** The approver is the squad leader for a group
  match and the booker otherwise; visibility comes from the booking plus the squad's
  ``accepts_public_requests``. Storing either would let them drift from the booking.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from apps.bookings.models import ACTIVE_BOOKING_STATUSES, BookingMode, BookingVisibility
from apps.core.utils import now
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify, notify_many

from .models import (
    JoinRequest,
    Match,
    MatchInvite,
    MatchPlayer,
    MatchStatus,
    MatchVisibility,
    Squad,
    SquadInvite,
    SquadMembership,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Squads
# ---------------------------------------------------------------------------
def unique_squad_slug(name: str) -> str:
    base = slugify(name)[:82] or "squad"
    slug = base
    suffix = 2
    while Squad.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@transaction.atomic
def create_squad(*, leader, name: str, sports=None, **fields) -> Squad:
    """Create a squad with its leader already a member.

    The leader membership is created in the same transaction for the same reason a turf
    gets its owner membership: every permission check goes through membership, so a
    squad without one would be unreachable by the person who just made it.
    """
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": "A squad name is required."})

    squad = Squad.objects.create(
        name=name, slug=unique_squad_slug(name), leader=leader, created_by=leader, **fields
    )
    if sports:
        squad.sports.set(sports)

    SquadMembership.objects.create(
        squad=squad,
        player=leader,
        role=SquadMembership.Role.LEADER,
        status=SquadMembership.Status.ACTIVE,
        joined_at=now(),
    )
    logger.info("Squad created", extra={"squad": str(squad.id)})
    return squad


def squad_membership(*, squad: Squad, user) -> SquadMembership | None:
    if not user or not user.is_authenticated:
        return None
    return squad.memberships.filter(player=user, status=SquadMembership.Status.ACTIVE).first()


def is_squad_member(*, squad: Squad, user) -> bool:
    return squad_membership(squad=squad, user=user) is not None


def is_squad_leader(*, squad: Squad, user) -> bool:
    return bool(user and user.is_authenticated and squad.leader_id == user.id)


def active_squad_members(squad: Squad):
    return squad.memberships.filter(status=SquadMembership.Status.ACTIVE).select_related("player")


@transaction.atomic
def make_or_get_squad_membership(*, squad: Squad, player, role: str = SquadMembership.Role.MEMBER):
    """Put a player in a squad directly. Used by seeding and by "also add to squad"."""
    membership, _ = SquadMembership.objects.get_or_create(
        squad=squad,
        player=player,
        status=SquadMembership.Status.ACTIVE,
        defaults={"role": role, "joined_at": now()},
    )
    return membership


@transaction.atomic
def invite_to_squad(*, squad: Squad, invited_by, player, message: str = "") -> SquadInvite:
    if not is_squad_leader(squad=squad, user=invited_by) and not is_squad_member(
        squad=squad, user=invited_by
    ):
        raise ValidationError({"squad": "Only squad members can invite."})
    if is_squad_member(squad=squad, user=player):
        raise ValidationError({"player": "They are already in this squad."})
    if squad.invites.filter(player=player, status=SquadInvite.Status.PENDING).exists():
        raise ValidationError({"player": "They already have a pending invitation."})

    invite = SquadInvite.objects.create(
        squad=squad, player=player, invited_by=invited_by, message=message.strip()[:300]
    )
    notify(
        user=player,
        kind=NotificationKind.SQUAD_INVITE,
        url=f"/squads/{squad.slug}",
        data={"squad_id": str(squad.id), "invite_id": str(invite.id)},
        squad=squad.name,
        inviter=getattr(invited_by, "full_name", "") or "A squad member",
    )
    return invite


@transaction.atomic
def respond_to_squad_invite(*, invite: SquadInvite, user, accept: bool) -> SquadInvite:
    if invite.player_id != user.id:
        raise ValidationError({"player": "This invitation is for someone else."})
    if invite.status != SquadInvite.Status.PENDING:
        raise ValidationError({"status": "This invitation is no longer open."})

    invite.status = SquadInvite.Status.ACCEPTED if accept else SquadInvite.Status.DECLINED
    invite.decided_at = now()
    invite.save(update_fields=["status", "decided_at", "updated_at"])

    if accept:
        SquadMembership.objects.update_or_create(
            squad=invite.squad,
            player=user,
            status=SquadMembership.Status.ACTIVE,
            defaults={"role": SquadMembership.Role.MEMBER, "joined_at": now()},
        )
        notify(
            user=invite.squad.leader,
            kind=NotificationKind.SQUAD_JOINED,
            url=f"/squads/{invite.squad.slug}",
            data={"squad_id": str(invite.squad.id)},
            squad=invite.squad.name,
            player=getattr(user, "full_name", "") or "A player",
        )
    return invite


@transaction.atomic
def leave_squad(*, squad: Squad, user) -> None:
    """Leave a squad. The leader must hand over first — a squad needs one."""
    if is_squad_leader(squad=squad, user=user):
        raise ValidationError({"leader": "Transfer leadership before leaving your own squad."})

    membership = squad_membership(squad=squad, user=user)
    if membership is None:
        return
    membership.status = SquadMembership.Status.LEFT
    membership.save(update_fields=["status", "updated_at"])


@transaction.atomic
def remove_squad_member(*, squad: Squad, actor, player) -> None:
    if not is_squad_leader(squad=squad, user=actor):
        raise ValidationError({"squad": "Only the leader can remove members."})
    if player.id == squad.leader_id:
        raise ValidationError({"player": "The leader cannot be removed."})

    membership = squad_membership(squad=squad, user=player)
    if membership is None:
        return
    membership.status = SquadMembership.Status.REMOVED
    membership.save(update_fields=["status", "updated_at"])


@transaction.atomic
def transfer_squad_leadership(*, squad: Squad, actor, new_leader) -> Squad:
    if not is_squad_leader(squad=squad, user=actor):
        raise ValidationError({"squad": "Only the leader can hand over."})
    if not is_squad_member(squad=squad, user=new_leader):
        raise ValidationError({"player": "They are not in this squad."})

    squad.memberships.filter(player=actor, status=SquadMembership.Status.ACTIVE).update(
        role=SquadMembership.Role.MEMBER
    )
    squad.memberships.filter(player=new_leader, status=SquadMembership.Status.ACTIVE).update(
        role=SquadMembership.Role.LEADER
    )
    squad.leader = new_leader
    squad.save(update_fields=["leader", "updated_at"])
    return squad


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------
def resolve_visibility(*, booking, squad: Squad | None) -> str:
    """Derive the match's visibility from the booking and the squad (DOMAIN §6)."""
    if booking.mode == BookingMode.GROUP and squad is not None:
        return MatchVisibility.BOARD if squad.accepts_public_requests else MatchVisibility.SQUAD
    return (
        MatchVisibility.BOARD
        if booking.visibility == BookingVisibility.PUBLIC
        else MatchVisibility.PRIVATE
    )


def resolve_capacity(*, booking) -> int:
    """``players_per_side x 2``, capped by the ground (DOMAIN §6)."""
    from_format = booking.sport_format.players_per_side * 2
    return max(2, min(from_format, booking.ground.max_players))


@transaction.atomic
def create_match_for_booking(*, booking, squad: Squad | None = None) -> Match:
    """Every booking creates exactly one match (DOMAIN §6).

    Idempotent: a retried booking creation must not produce a second match.
    """
    existing = Match.objects.filter(booking=booking).first()
    if existing is not None:
        return existing

    match = Match.objects.create(
        booking=booking,
        squad=squad,
        sport=booking.sport,
        sport_format=booking.sport_format,
        capacity=resolve_capacity(booking=booking),
        visibility=resolve_visibility(booking=booking, squad=squad),
        notes=booking.notes,
    )

    # The booker is on the roster unless they booked as staff for a walk-in — in that
    # case the person playing has no account and the cashier is not playing.
    if not booking.booked_for_name:
        MatchPlayer.objects.create(
            match=match, player=booking.booked_by, source=MatchPlayer.Source.BOOKER
        )

    if squad is not None:
        _seed_squad_roster(match=match, squad=squad, skip=booking.booked_by)

    logger.info(
        "Match created",
        extra={"match": str(match.id), "visibility": match.visibility},
    )
    return match


def _seed_squad_roster(*, match: Match, squad: Squad, skip) -> None:
    """Put the squad's active members on the roster, up to capacity.

    Everyone added is notified and can drop out — a squad booking is an invitation to
    play, not a summons.
    """
    members = [
        membership.player
        for membership in active_squad_members(squad)
        if membership.player_id != skip.id
    ]
    room = match.capacity - match.players.count()
    added = []
    for player in members[: max(0, room)]:
        _, created = MatchPlayer.objects.get_or_create(
            match=match, player=player, defaults={"source": MatchPlayer.Source.SQUAD}
        )
        if created:
            added.append(player)

    notify_many(
        users=added,
        kind=NotificationKind.MATCH_ADDED,
        url=f"/matches/{match.id}",
        data={"match_id": str(match.id)},
        **_match_context(match),
    )


def _match_context(match: Match) -> dict:
    from apps.core.utils import DHAKA

    local = match.starts_at.astimezone(DHAKA)
    return {
        "turf": match.turf.name,
        "ground": match.ground.name,
        "when": local.strftime("%a %d %b, %H:%M"),
        "sport": match.sport.name,
        "needed": match.needed,
        "organiser": getattr(match.organiser, "full_name", "") or "The organiser",
    }


def _match_url(match: Match) -> str:
    return f"/matches/{match.id}"


@transaction.atomic
def sync_match_with_booking(*, booking) -> Match | None:
    """Keep the match's status in step with its booking.

    Called whenever a booking transitions. A cancelled booking means a cancelled match —
    leaving it ``upcoming`` would keep it on the board advertising a ground nobody holds.
    """
    match = Match.objects.filter(booking=booking).select_related("booking").first()
    if match is None:
        return None

    if booking.status not in ACTIVE_BOOKING_STATUSES and match.status != MatchStatus.CANCELLED:
        match.status = MatchStatus.CANCELLED
        match.save(update_fields=["status", "updated_at"])
        expire_pending_for_match(match=match, reason="The booking was cancelled.")
    return match


# ---------------------------------------------------------------------------
# Who may see and do what (DOMAIN §6)
# ---------------------------------------------------------------------------
def is_on_roster(*, match: Match, user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return match.players.filter(player=user).exists()


def is_organiser(*, match: Match, user) -> bool:
    """The person who approves: the squad leader, or the booker."""
    if not user or not user.is_authenticated:
        return False
    return match.organiser.id == user.id


def can_view_match(*, match: Match, user) -> bool:
    """A player may always see a match they are in, or one on the board."""
    if is_on_roster(match=match, user=user) or is_organiser(match=match, user=user):
        return True
    if match.visibility == MatchVisibility.BOARD:
        return True
    if match.visibility == MatchVisibility.SQUAD and match.squad_id:
        return is_squad_member(squad=match.squad, user=user)
    # Private: invitees need to see what they were invited to.
    return match.invites.filter(
        invited_player=user, status=MatchInvite.Status.LEADER_APPROVED
    ).exists()


def can_request_to_join(*, match: Match, user) -> tuple[bool, str]:
    """Whether this player may ask to join, and why not when they may not.

    Returns a reason rather than just a boolean so the UI can say "this match is full"
    instead of hiding the button with no explanation.
    """
    if match.visibility != MatchVisibility.BOARD:
        return False, "This match is not open to requests."
    if match.status != MatchStatus.UPCOMING:
        return False, "This match is not upcoming."
    if match.starts_at <= now():
        return False, "This match has already started."
    if is_on_roster(match=match, user=user):
        return False, "You are already playing."
    if match.is_full:
        return False, "This match is full."
    if match.join_requests.filter(player=user, status=JoinRequest.Status.PENDING).exists():
        return False, "You have already asked to join."
    if _has_clashing_match(user=user, match=match):
        return False, "You are already playing elsewhere at that time."
    return True, ""


def _has_clashing_match(*, user, match: Match) -> bool:
    """One player cannot be in two places at once (DOMAIN §6 capacity rules)."""
    from psycopg.types.range import TimestamptzRange

    return (
        MatchPlayer.objects.filter(player=user)
        .exclude(match=match)
        .filter(
            match__status=MatchStatus.UPCOMING,
            match__booking__status__in=ACTIVE_BOOKING_STATUSES,
            match__booking__time_range__overlap=TimestamptzRange(match.starts_at, match.ends_at),
        )
        .exists()
    )


# ---------------------------------------------------------------------------
# Roster changes — all under a row lock
# ---------------------------------------------------------------------------
def _locked(match: Match) -> Match:
    """Re-read the match FOR UPDATE, so capacity is decided one caller at a time."""
    return Match.objects.select_for_update().select_related("booking").get(pk=match.pk)


@transaction.atomic
def add_player(*, match: Match, player, source: str) -> MatchPlayer:
    """Put a player on the roster, refusing to exceed capacity.

    The lock is the point: two approvals for the last spot must not both succeed.
    """
    locked = _locked(match)
    if locked.status != MatchStatus.UPCOMING:
        raise ValidationError({"match": "This match is no longer open."})
    if locked.players.filter(player=player).exists():
        raise ValidationError({"player": "They are already on the roster."})
    if locked.players.count() >= locked.capacity:
        raise ValidationError({"match": "This match is full."})

    entry = MatchPlayer.objects.create(match=locked, player=player, source=source)
    logger.info("Player added to match", extra={"match": str(locked.id), "source": source})
    return entry


@transaction.atomic
def leave_match(*, match: Match, user) -> None:
    """Drop out. The organiser cannot — they hold the booking (or lead the squad)."""
    if is_organiser(match=match, user=user):
        raise ValidationError({"match": "Cancel the booking instead; the organiser cannot leave."})

    entry = match.players.filter(player=user).first()
    if entry is None:
        return

    entry.delete()
    notify(
        user=match.organiser,
        kind=NotificationKind.MATCH_PLAYER_LEFT,
        url=_match_url(match),
        data={"match_id": str(match.id)},
        player=getattr(user, "full_name", "") or "A player",
        **_match_context(match),
    )


@transaction.atomic
def remove_player(*, match: Match, actor, player) -> None:
    if not is_organiser(match=match, user=actor):
        raise ValidationError({"match": "Only the organiser can remove players."})
    if player.id == match.organiser.id:
        raise ValidationError({"player": "The organiser cannot be removed."})

    entry = match.players.filter(player=player).first()
    if entry is None:
        return
    entry.delete()
    notify(
        user=player,
        kind=NotificationKind.MATCH_REMOVED,
        url=_match_url(match),
        data={"match_id": str(match.id)},
        **_match_context(match),
    )


# ---------------------------------------------------------------------------
# Join requests
# ---------------------------------------------------------------------------
@transaction.atomic
def request_to_join(*, match: Match, user, message: str = "") -> JoinRequest:
    allowed, reason = can_request_to_join(match=match, user=user)
    if not allowed:
        raise ValidationError({"match": reason})

    request = JoinRequest.objects.create(match=match, player=user, message=message.strip()[:300])
    notify(
        user=match.organiser,
        kind=NotificationKind.MATCH_JOIN_REQUEST,
        url=_match_url(match),
        data={"match_id": str(match.id), "request_id": str(request.id)},
        player=getattr(user, "full_name", "") or "A player",
        **_match_context(match),
    )
    return request


@transaction.atomic
def decide_join_request(
    *, request: JoinRequest, approver, approve: bool, add_to_squad: bool = False, note: str = ""
) -> JoinRequest:
    """Approve or decline. Approval adds the player to the roster (DOMAIN §6).

    ``add_to_squad`` is the leader's option to keep a good player around after the match
    — the phase brief's "also add to squad" checkbox.
    """
    match = request.match
    if not is_organiser(match=match, user=approver):
        raise ValidationError({"approver": "Only the organiser can decide this."})
    if request.status != JoinRequest.Status.PENDING:
        raise ValidationError({"status": "This request has already been decided."})

    if approve:
        # Raises when the last spot has gone, which is exactly the race the lock exists
        # for: the request stays pending so the organiser sees why nothing happened.
        add_player(match=match, player=request.player, source=MatchPlayer.Source.REQUEST)

    request.status = JoinRequest.Status.APPROVED if approve else JoinRequest.Status.DECLINED
    request.decided_by = approver
    request.decided_at = now()
    request.decision_note = note.strip()[:300]
    request.save(
        update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"]
    )

    if approve and add_to_squad and match.squad_id:
        SquadMembership.objects.get_or_create(
            squad=match.squad,
            player=request.player,
            status=SquadMembership.Status.ACTIVE,
            defaults={"role": SquadMembership.Role.MEMBER, "joined_at": now()},
        )

    notify(
        user=request.player,
        kind=(
            NotificationKind.MATCH_JOIN_APPROVED
            if approve
            else NotificationKind.MATCH_JOIN_DECLINED
        ),
        url=_match_url(match),
        data={"match_id": str(match.id)},
        **_match_context(match),
    )
    return request


@transaction.atomic
def withdraw_join_request(*, request: JoinRequest, user) -> JoinRequest:
    if request.player_id != user.id:
        raise ValidationError({"player": "This request is not yours."})
    if request.status != JoinRequest.Status.PENDING:
        raise ValidationError({"status": "This request has already been decided."})

    request.status = JoinRequest.Status.WITHDRAWN
    request.decided_at = now()
    request.save(update_fields=["status", "decided_at", "updated_at"])
    return request


# ---------------------------------------------------------------------------
# Invites (DECISIONS D1)
# ---------------------------------------------------------------------------
def _can_propose(*, match: Match, user) -> bool:
    """Squad members may propose; for a non-squad match only the booker invites."""
    if match.squad_id:
        return is_squad_member(squad=match.squad, user=user)
    return is_organiser(match=match, user=user)


@transaction.atomic
def invite_player(*, match: Match, invited_by, player, message: str = "") -> MatchInvite:
    """Invite somebody, starting at the right point in the chain (DECISIONS D1).

    A member of a **closed** squad can only *propose* — the leader approves, then the
    player accepts. An invite from the organiser skips straight to awaiting the player,
    because there is nobody left to ask.
    """
    if match.status != MatchStatus.UPCOMING:
        raise ValidationError({"match": "This match is no longer open."})
    if match.starts_at <= now():
        raise ValidationError({"match": "This match has already started."})
    if not _can_propose(match=match, user=invited_by):
        raise ValidationError({"match": "You cannot invite players to this match."})
    if is_on_roster(match=match, user=player):
        raise ValidationError({"player": "They are already playing."})
    if match.is_full:
        raise ValidationError({"match": "This match is full."})
    if match.invites.filter(
        invited_player=player,
        status__in=[MatchInvite.Status.PROPOSED, MatchInvite.Status.LEADER_APPROVED],
    ).exists():
        raise ValidationError({"player": "They already have a live invitation."})

    straight_through = is_organiser(match=match, user=invited_by)
    invite = MatchInvite.objects.create(
        match=match,
        invited_player=player,
        invited_by=invited_by,
        message=message.strip()[:300],
        status=(
            MatchInvite.Status.LEADER_APPROVED if straight_through else MatchInvite.Status.PROPOSED
        ),
        approved_by=invited_by if straight_through else None,
    )

    if straight_through:
        notify(
            user=player,
            kind=NotificationKind.MATCH_INVITE,
            url=_match_url(match),
            data={"match_id": str(match.id), "invite_id": str(invite.id)},
            **_match_context(match),
        )
    else:
        notify(
            user=match.organiser,
            kind=NotificationKind.MATCH_INVITE_PROPOSED,
            url=_match_url(match),
            data={"match_id": str(match.id), "invite_id": str(invite.id)},
            player=getattr(player, "full_name", "") or "A player",
            proposer=getattr(invited_by, "full_name", "") or "A squad member",
            **_match_context(match),
        )
    return invite


@transaction.atomic
def decide_proposed_invite(*, invite: MatchInvite, leader, approve: bool) -> MatchInvite:
    """``proposed -> leader_approved | rejected`` (DECISIONS D1)."""
    if not is_organiser(match=invite.match, user=leader):
        raise ValidationError({"leader": "Only the organiser can decide this."})
    if invite.status != MatchInvite.Status.PROPOSED:
        raise ValidationError({"status": "This proposal has already been decided."})

    invite.status = MatchInvite.Status.LEADER_APPROVED if approve else MatchInvite.Status.REJECTED
    invite.approved_by = leader
    invite.decided_at = now()
    invite.save(update_fields=["status", "approved_by", "decided_at", "updated_at"])

    if approve:
        notify(
            user=invite.invited_player,
            kind=NotificationKind.MATCH_INVITE,
            url=_match_url(invite.match),
            data={"match_id": str(invite.match.id), "invite_id": str(invite.id)},
            **_match_context(invite.match),
        )
    return invite


@transaction.atomic
def respond_to_invite(*, invite: MatchInvite, user, accept: bool) -> MatchInvite:
    """``leader_approved -> accepted | declined``. Accepting adds them to the roster."""
    if invite.invited_player_id != user.id:
        raise ValidationError({"player": "This invitation is for someone else."})
    if invite.status != MatchInvite.Status.LEADER_APPROVED:
        raise ValidationError({"status": "This invitation is not awaiting you."})

    if accept:
        if _has_clashing_match(user=user, match=invite.match):
            raise ValidationError({"match": "You are already playing elsewhere at that time."})
        add_player(match=invite.match, player=user, source=MatchPlayer.Source.INVITE)

    invite.status = MatchInvite.Status.ACCEPTED if accept else MatchInvite.Status.DECLINED
    invite.decided_at = now()
    invite.save(update_fields=["status", "decided_at", "updated_at"])

    notify(
        user=invite.match.organiser,
        kind=(
            NotificationKind.MATCH_INVITE_ACCEPTED
            if accept
            else NotificationKind.MATCH_INVITE_DECLINED
        ),
        url=_match_url(invite.match),
        data={"match_id": str(invite.match.id)},
        player=getattr(user, "full_name", "") or "A player",
        **_match_context(invite.match),
    )
    return invite


# ---------------------------------------------------------------------------
# Expiry (Celery beat)
# ---------------------------------------------------------------------------
def expire_pending_for_match(*, match: Match, reason: str = "") -> int:
    """Close out everything still pending on a match. Returns how many."""
    closed = match.join_requests.filter(status=JoinRequest.Status.PENDING).update(
        status=JoinRequest.Status.EXPIRED, decided_at=now(), decision_note=reason[:300]
    )
    closed += match.invites.filter(
        status__in=[MatchInvite.Status.PROPOSED, MatchInvite.Status.LEADER_APPROVED]
    ).update(status=MatchInvite.Status.EXPIRED, decided_at=now())
    return closed


def expire_started_matches() -> int:
    """Requests and invites expire at match start (DOMAIN §6)."""
    started = (
        Match.objects.filter(
            status=MatchStatus.UPCOMING, booking__time_range__startswith__lte=now()
        )
        .filter(
            Q(join_requests__status=JoinRequest.Status.PENDING)
            | Q(
                invites__status__in=[
                    MatchInvite.Status.PROPOSED,
                    MatchInvite.Status.LEADER_APPROVED,
                ]
            )
        )
        .distinct()
    )

    total = 0
    for match in started:
        total += expire_pending_for_match(match=match, reason="The match has started.")
    return total


def advance_match_statuses() -> int:
    """Move matches to ``in_progress`` and ``finished`` as their slot passes."""
    moment = now()
    started = Match.objects.filter(
        status=MatchStatus.UPCOMING,
        booking__time_range__startswith__lte=moment,
        booking__time_range__endswith__gt=moment,
    ).update(status=MatchStatus.IN_PROGRESS)

    finished = Match.objects.filter(
        status__in=[MatchStatus.UPCOMING, MatchStatus.IN_PROGRESS],
        booking__time_range__endswith__lte=moment,
    ).update(status=MatchStatus.FINISHED)

    return started + finished
