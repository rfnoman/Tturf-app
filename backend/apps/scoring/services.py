"""Scorecard, MOTM and peer-rating business logic (DOMAIN §7, DECISIONS D6/D7).

``Scorecard.status`` is a state machine:

    draft -> submitted -> confirmed -> locked
    submitted -> disputed -> confirmed   (staff or admin resolves)

Every transition is one function here that validates the from-state, writes the new one
and records a ``ScorecardEvent``. ``locked`` is terminal on purpose: Phase 06 computes
ratings from a locked scorecard, and a number that can move afterwards is worse than no
number at all. Locking fires ``scorecard_locked``, which is the seam Phase 06 attaches to.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.utils import now
from apps.matches.models import Match, MatchStatus
from apps.matches.services import is_organiser
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify, notify_many
from apps.sports.models import StatDefinition
from apps.turfs.services import TURF_STAFF_ROLES, has_turf_role

from .hooks import scorecard_locked
from .models import (
    MatchResult,
    MatchTeam,
    MatchTeamPlayer,
    MotmVote,
    PeerRating,
    PlayerStat,
    Scorecard,
    ScorecardEvent,
    ScorecardStatus,
    TeamSide,
)
from .validators import ScorecardData, validate_scorecard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Who may do what
# ---------------------------------------------------------------------------
def is_turf_staff(*, match: Match, user) -> bool:
    return has_turf_role(turf=match.turf, user=user, roles=TURF_STAFF_ROLES)


def is_captain(*, match: Match, user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return match.teams.filter(captain=user).exists()


def can_manage_teams(*, match: Match, user) -> bool:
    """The organiser or turf staff pick the sides."""
    return is_organiser(match=match, user=user) or is_turf_staff(match=match, user=user)


def can_score(*, match: Match, user) -> bool:
    """DOMAIN §7: the scorer, the organiser, a captain, or turf staff."""
    scorecard = Scorecard.objects.filter(match=match).only("scorer").first()
    if scorecard is not None and scorecard.scorer_id == getattr(user, "id", None):
        return True
    return (
        is_organiser(match=match, user=user)
        or is_captain(match=match, user=user)
        or is_turf_staff(match=match, user=user)
    )


def confirming_side(scorecard: Scorecard):
    """The team whose captain confirms: the one the scorer is **not** on.

    DOMAIN §7 says "the opposing captain confirms", which only means anything if we can
    say which side the scorer was on. A scorer who did not play (turf staff) leaves this
    ambiguous, so either captain may confirm in that case.
    """
    entry = (
        MatchTeamPlayer.objects.filter(
            team__match=scorecard.match, match_player__player=scorecard.scorer
        )
        .select_related("team")
        .first()
    )
    if entry is None:
        return None
    other = TeamSide.B if entry.team.side == TeamSide.A else TeamSide.A
    return scorecard.match.teams.filter(side=other).first()


def can_confirm(*, scorecard: Scorecard, user) -> bool:
    if is_turf_staff(match=scorecard.match, user=user):
        return True
    if scorecard.scorer_id == getattr(user, "id", None):
        # The scorer confirming their own card would defeat the point.
        return False

    opposing = confirming_side(scorecard)
    if opposing is None:
        # Scorer did not play: either captain may confirm.
        return is_captain(match=scorecard.match, user=user)
    return opposing.captain_id == getattr(user, "id", None)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
@transaction.atomic
def ensure_teams(*, match: Match) -> list[MatchTeam]:
    """Both sides exist. Idempotent, so the team builder can call it freely."""
    for side in (TeamSide.A, TeamSide.B):
        MatchTeam.objects.get_or_create(match=match, side=side)
    return list(match.teams.order_by("side"))


@transaction.atomic
def set_teams(*, match: Match, assignments: dict, actor=None) -> list[MatchTeam]:
    """Place roster players on sides.

    ``assignments`` is ``{match_player_id: "A"|"B"}``. Anyone left out is taken off a
    team sheet — a player who turned up and did not play belongs on neither.
    """
    if not can_manage_teams(match=match, user=actor):
        raise ValidationError({"match": "Only the organiser or turf staff can set teams."})

    teams = {team.side: team for team in ensure_teams(match=match)}
    roster = {str(entry.id): entry for entry in match.players.all()}

    unknown = set(map(str, assignments)) - set(roster)
    if unknown:
        raise ValidationError({"assignments": "Those players are not on the roster."})

    MatchTeamPlayer.objects.filter(team__match=match).delete()
    for raw_id, side in assignments.items():
        if side not in TeamSide.values:
            raise ValidationError({"assignments": f"“{side}” is not a side."})
        MatchTeamPlayer.objects.create(team=teams[side], match_player=roster[str(raw_id)])

    return list(match.teams.order_by("side"))


@transaction.atomic
def set_captain(*, match: Match, side: str, player, actor=None) -> MatchTeam:
    if not can_manage_teams(match=match, user=actor):
        raise ValidationError({"match": "Only the organiser or turf staff can do that."})

    team = match.teams.filter(side=side).first()
    if team is None:
        raise ValidationError({"side": "That side does not exist yet."})
    if player is not None and not team.players.filter(match_player__player=player).exists():
        raise ValidationError({"player": "The captain has to be on that team."})

    team.captain = player
    team.save(update_fields=["captain", "updated_at"])
    return team


def player_rating(match: Match, user) -> int:
    """This player's overall in the match's sport, for balancing. 50 when unrated."""
    profile = getattr(user, "player_profile", None)
    if profile is None:
        return 50
    rating = next((r for r in profile.sport_ratings.all() if r.sport_id == match.sport_id), None)
    return rating.overall if rating else 50


@transaction.atomic
def auto_balance_teams(
    *, match: Match, actor=None, keep_squad_together: bool = False
) -> list[MatchTeam]:
    """Split the roster into two sides of comparable strength.

    Greedy: sort by rating descending and give each player to whichever side is currently
    weaker. For a two-way split that lands within one player's rating of optimal, which
    is well inside the noise of a self-assessed rating — and it is explicable to a player
    who asks why they are on this team, which a cleverer algorithm would not be.
    """
    if not can_manage_teams(match=match, user=actor):
        raise ValidationError({"match": "Only the organiser or turf staff can set teams."})

    teams = {team.side: team for team in ensure_teams(match=match)}
    roster = list(match.players.select_related("player", "player__player_profile"))
    if not roster:
        raise ValidationError({"match": "Nobody is on the roster yet."})

    ranked = sorted(roster, key=lambda entry: -player_rating(match, entry.player))

    MatchTeamPlayer.objects.filter(team__match=match).delete()
    totals = {TeamSide.A: 0, TeamSide.B: 0}
    counts = {TeamSide.A: 0, TeamSide.B: 0}
    half = (len(ranked) + 1) // 2

    for entry in ranked:
        # Keep the sides the same size first, then balance strength.
        if counts[TeamSide.A] >= half:
            side = TeamSide.B
        elif counts[TeamSide.B] >= half:
            side = TeamSide.A
        else:
            side = TeamSide.A if totals[TeamSide.A] <= totals[TeamSide.B] else TeamSide.B

        MatchTeamPlayer.objects.create(team=teams[side], match_player=entry)
        totals[side] += player_rating(match, entry.player)
        counts[side] += 1

    logger.info(
        "Teams auto-balanced",
        extra={"match": str(match.id), "a": totals[TeamSide.A], "b": totals[TeamSide.B]},
    )
    return list(match.teams.order_by("side"))


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------
@transaction.atomic
def get_or_create_scorecard(*, match: Match, actor=None) -> Scorecard:
    """The match's scorecard, created in draft with the organiser as scorer."""
    scorecard = Scorecard.objects.filter(match=match).first()
    if scorecard is not None:
        return scorecard
    return Scorecard.objects.create(match=match, scorer=match.organiser)


@transaction.atomic
def assign_scorer(*, scorecard: Scorecard, actor, scorer) -> Scorecard:
    """Hand scoring to a captain or turf staff (DOMAIN §7)."""
    if not can_manage_teams(match=scorecard.match, user=actor):
        raise ValidationError({"match": "Only the organiser or turf staff can reassign."})
    if not scorecard.is_editable:
        raise ValidationError({"status": "This scorecard is no longer being written."})

    allowed = (
        is_captain(match=scorecard.match, user=scorer)
        or is_turf_staff(match=scorecard.match, user=scorer)
        or is_organiser(match=scorecard.match, user=scorer)
    )
    if not allowed:
        raise ValidationError(
            {"scorer": "The scorer must be a captain, the organiser, or turf staff."}
        )

    scorecard.scorer = scorer
    scorecard.save(update_fields=["scorer", "updated_at"])
    return scorecard


def _definitions(match: Match) -> dict[str, StatDefinition]:
    return {
        definition.key: definition
        for definition in StatDefinition.objects.filter(sport=match.sport_id)
    }


def build_validation_data(*, scorecard: Scorecard, stats: dict | None = None) -> ScorecardData:
    """Assemble what the validators need from the stored (or proposed) values."""
    match = scorecard.match
    sides = {
        str(entry.match_player.player_id): entry.team.side
        for entry in MatchTeamPlayer.objects.filter(team__match=match).select_related(
            "team", "match_player"
        )
    }

    if stats is None:
        stats = {}
        for row in scorecard.player_stats.select_related("stat_definition"):
            stats.setdefault(str(row.player_id), {})[row.stat_definition.key] = row.value

    return ScorecardData(
        sport_slug=match.sport.slug,
        team_a_score=scorecard.team_a_score,
        team_b_score=scorecard.team_b_score,
        player_stats={
            str(key): {stat: Decimal(str(value)) for stat, value in values.items()}
            for key, values in stats.items()
        },
        player_sides=sides,
        team_stats=scorecard.extra or {},
        definitions=_definitions(match),
    )


def _resolve_result(scorecard: Scorecard) -> str:
    if scorecard.team_a_score > scorecard.team_b_score:
        return MatchResult.TEAM_A
    if scorecard.team_b_score > scorecard.team_a_score:
        return MatchResult.TEAM_B
    return MatchResult.DRAW


def record_event(
    *, scorecard: Scorecard, from_status: str, to_status: str, actor=None, note: str = ""
):
    return ScorecardEvent.objects.create(
        scorecard=scorecard,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        note=note[:300],
    )


@transaction.atomic
def save_draft(
    *, scorecard: Scorecard, actor, team_a_score=None, team_b_score=None, stats=None, extra=None
) -> Scorecard:
    """Write the scorer's numbers without submitting them.

    Deliberately **unvalidated** beyond the field types: a scorer at the ground filling
    in a phone form should not be blocked halfway through because the goals do not add
    up yet. Validation runs at submit.
    """
    if not can_score(match=scorecard.match, user=actor):
        raise ValidationError({"match": "You are not scoring this match."})
    if not scorecard.is_editable:
        raise ValidationError({"status": "This scorecard can no longer be edited."})

    if team_a_score is not None:
        scorecard.team_a_score = int(team_a_score)
    if team_b_score is not None:
        scorecard.team_b_score = int(team_b_score)
    if extra is not None:
        scorecard.extra = extra
    scorecard.result = _resolve_result(scorecard)
    scorecard.save(update_fields=["team_a_score", "team_b_score", "extra", "result", "updated_at"])

    if stats is not None:
        _write_stats(scorecard=scorecard, stats=stats)

    return scorecard


def _write_stats(*, scorecard: Scorecard, stats: dict) -> None:
    """Replace this scorecard's player stats with ``{player_id: {key: value}}``.

    Only roster players, and only stats the sport defines — a scorer cannot invent
    either, whatever the client sends.
    """
    definitions = _definitions(scorecard.match)
    roster = {
        str(entry.player_id): entry.player
        for entry in scorecard.match.players.select_related("player")
    }

    unknown_players = set(map(str, stats)) - set(roster)
    if unknown_players:
        raise ValidationError({"stats": "Only players on the roster can be given stats."})

    PlayerStat.objects.filter(scorecard=scorecard).delete()
    rows = []
    for raw_id, values in stats.items():
        player = roster[str(raw_id)]
        for key, value in values.items():
            definition = definitions.get(key)
            if definition is None:
                raise ValidationError(
                    {"stats": f"{scorecard.match.sport.name} has no stat called “{key}”."}
                )
            rows.append(
                PlayerStat(
                    scorecard=scorecard,
                    player=player,
                    stat_definition=definition,
                    value=Decimal(str(value)),
                )
            )
    PlayerStat.objects.bulk_create(rows)


@transaction.atomic
def submit_scorecard(*, scorecard: Scorecard, actor, note: str = "") -> Scorecard:
    """``draft|disputed -> submitted``, running the sport's validators first."""
    if not can_score(match=scorecard.match, user=actor):
        raise ValidationError({"match": "You are not scoring this match."})
    if not scorecard.is_editable:
        raise ValidationError({"status": "This scorecard has already been submitted."})
    if not MatchTeamPlayer.objects.filter(team__match=scorecard.match).exists():
        raise ValidationError({"teams": "Split the roster into two teams first."})

    issues = validate_scorecard(build_validation_data(scorecard=scorecard))
    if issues:
        # Grouped by field so the form can show each message against its input.
        grouped: dict[str, list[str]] = {}
        for issue in issues:
            grouped.setdefault(issue.field, []).append(issue.message)
        raise ValidationError(grouped)

    previous = scorecard.status
    scorecard.status = ScorecardStatus.SUBMITTED
    scorecard.submitted_at = now()
    scorecard.result = _resolve_result(scorecard)
    scorecard.dispute_reason = ""
    # DECISIONS D7: a card entered by turf staff is verified from the outset.
    if is_turf_staff(match=scorecard.match, user=actor):
        scorecard.verified_by_staff = True
    scorecard.save()

    record_event(
        scorecard=scorecard,
        from_status=previous,
        to_status=scorecard.status,
        actor=actor,
        note=note,
    )
    _mark_attendance(scorecard)

    opposing = confirming_side(scorecard)
    recipients = (
        [opposing.captain]
        if opposing and opposing.captain
        else [team.captain for team in scorecard.match.teams.all() if team.captain]
    )
    notify_many(
        users=[user for user in recipients if user and user.id != actor.id],
        kind=NotificationKind.SCORECARD_SUBMITTED,
        url=f"/matches/{scorecard.match_id}/scorecard",
        data={"match_id": str(scorecard.match_id)},
        **_context(scorecard),
    )
    logger.info("Scorecard submitted", extra={"scorecard": str(scorecard.id)})
    return scorecard


def _mark_attendance(scorecard: Scorecard) -> None:
    """A roster player with any stat played; the rest are marked absent.

    Phase 06 and the fitness layer both need to know who actually turned up, and the
    scorecard is the only place that knows.
    """
    played = set(scorecard.player_stats.values_list("player_id", flat=True).distinct())
    on_a_team = set(
        MatchTeamPlayer.objects.filter(team__match=scorecard.match).values_list(
            "match_player__player_id", flat=True
        )
    )
    for entry in scorecard.match.players.all():
        attended = entry.player_id in played or entry.player_id in on_a_team
        if entry.attended != attended:
            entry.attended = attended
            entry.save(update_fields=["attended", "updated_at"])


def _context(scorecard: Scorecard) -> dict:
    match = scorecard.match
    return {
        "turf": match.turf.name,
        "sport": match.sport.name,
        "score": f"{scorecard.team_a_score}–{scorecard.team_b_score}",
        "reason": scorecard.dispute_reason or "",
        "player": "",
    }


@transaction.atomic
def confirm_scorecard(
    *, scorecard: Scorecard, actor=None, auto: bool = False, already_authorised: bool = False
) -> Scorecard:
    """``submitted|disputed -> confirmed``, then locked immediately (DOMAIN §7).

    ``already_authorised`` is for :func:`resolve_dispute`, which admits a wider set of
    actors than confirmation does — a platform admin may settle a dispute without being
    the opposing captain or turf staff at that turf. Re-running the confirmation check
    there would reject the very person the escalation exists to involve.
    """
    if scorecard.status not in (ScorecardStatus.SUBMITTED, ScorecardStatus.DISPUTED):
        raise ValidationError({"status": "This scorecard is not awaiting confirmation."})
    if not auto and not already_authorised and not can_confirm(scorecard=scorecard, user=actor):
        raise ValidationError({"actor": "Only the opposing captain or turf staff can confirm."})

    previous = scorecard.status
    scorecard.status = ScorecardStatus.CONFIRMED
    scorecard.confirmed_by = actor
    scorecard.confirmed_at = now()
    scorecard.auto_confirmed = auto
    if actor is not None and is_turf_staff(match=scorecard.match, user=actor):
        scorecard.verified_by_staff = True
    scorecard.save()

    record_event(
        scorecard=scorecard,
        from_status=previous,
        to_status=scorecard.status,
        actor=actor,
        note="Nobody acted within the window" if auto else "",
    )
    return lock_scorecard(scorecard=scorecard, actor=actor)


@transaction.atomic
def dispute_scorecard(*, scorecard: Scorecard, actor, reason: str) -> Scorecard:
    """``submitted -> disputed``. A reason is required; somebody has to act on it."""
    if scorecard.status != ScorecardStatus.SUBMITTED:
        raise ValidationError({"status": "Only a submitted scorecard can be disputed."})
    if not can_confirm(scorecard=scorecard, user=actor):
        raise ValidationError({"actor": "Only the opposing captain or turf staff can dispute."})

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Say what is wrong, so it can be fixed."})

    previous = scorecard.status
    scorecard.status = ScorecardStatus.DISPUTED
    scorecard.dispute_reason = reason[:300]
    scorecard.disputed_by = actor
    scorecard.save(update_fields=["status", "dispute_reason", "disputed_by", "updated_at"])

    record_event(
        scorecard=scorecard,
        from_status=previous,
        to_status=scorecard.status,
        actor=actor,
        note=reason,
    )
    notify_many(
        users=[scorecard.scorer, *_staff_users(scorecard.match)],
        kind=NotificationKind.SCORECARD_DISPUTED,
        url=f"/matches/{scorecard.match_id}/scorecard",
        data={"match_id": str(scorecard.match_id)},
        **_context(scorecard),
    )
    return scorecard


def _staff_users(match: Match) -> list:
    from apps.turfs.models import TurfMembership

    return [
        membership.user
        for membership in match.turf.memberships.filter(
            status=TurfMembership.Status.ACTIVE, user__isnull=False
        ).select_related("user")
    ]


@transaction.atomic
def resolve_dispute(
    *, scorecard: Scorecard, actor, team_a_score=None, team_b_score=None, stats=None
) -> Scorecard:
    """Turf staff or a platform admin settle a dispute, correcting it if needed.

    Resolution goes straight to confirmed: the whole point of escalating is that
    somebody neutral has now looked.
    """
    is_admin = bool(
        getattr(actor, "is_platform_admin", False) or getattr(actor, "is_superuser", False)
    )
    if not is_admin and not is_turf_staff(match=scorecard.match, user=actor):
        raise ValidationError({"actor": "Only turf staff or a platform admin can resolve this."})
    if scorecard.status != ScorecardStatus.DISPUTED:
        raise ValidationError({"status": "This scorecard is not disputed."})

    if team_a_score is not None:
        scorecard.team_a_score = int(team_a_score)
    if team_b_score is not None:
        scorecard.team_b_score = int(team_b_score)
    scorecard.result = _resolve_result(scorecard)
    scorecard.resolved_by = actor
    scorecard.save(
        update_fields=["team_a_score", "team_b_score", "result", "resolved_by", "updated_at"]
    )

    if stats is not None:
        _write_stats(scorecard=scorecard, stats=stats)

    issues = validate_scorecard(build_validation_data(scorecard=scorecard))
    if issues:
        grouped: dict[str, list[str]] = {}
        for issue in issues:
            grouped.setdefault(issue.field, []).append(issue.message)
        raise ValidationError(grouped)

    # A resolution by staff is a verified card (DECISIONS D7).
    scorecard.verified_by_staff = True
    scorecard.save(update_fields=["verified_by_staff", "updated_at"])
    return confirm_scorecard(scorecard=scorecard, actor=actor, already_authorised=True)


@transaction.atomic
def lock_scorecard(*, scorecard: Scorecard, actor=None) -> Scorecard:
    """``confirmed -> locked``. Terminal, and the seam Phase 06 attaches to."""
    if scorecard.status != ScorecardStatus.CONFIRMED:
        raise ValidationError({"status": "Only a confirmed scorecard can be locked."})

    previous = scorecard.status
    scorecard.status = ScorecardStatus.LOCKED
    scorecard.locked_at = now()
    scorecard.save(update_fields=["status", "locked_at", "updated_at"])

    record_event(scorecard=scorecard, from_status=previous, to_status=scorecard.status, actor=actor)

    if scorecard.match.status != MatchStatus.FINISHED:
        Match.objects.filter(pk=scorecard.match_id).update(status=MatchStatus.FINISHED)

    notify_many(
        users=[entry.player for entry in scorecard.match.players.select_related("player")],
        kind=NotificationKind.SCORECARD_LOCKED,
        url=f"/matches/{scorecard.match_id}/scorecard",
        data={"match_id": str(scorecard.match_id)},
        **_context(scorecard),
    )

    # Phase 06's rating engine subscribes here.
    scorecard_locked(scorecard=scorecard)
    logger.info("Scorecard locked", extra={"scorecard": str(scorecard.id)})
    return scorecard


# ---------------------------------------------------------------------------
# MOTM (DOMAIN §7)
# ---------------------------------------------------------------------------
def motm_window_closes_at(scorecard: Scorecard):
    if scorecard.submitted_at is None:
        return None
    return scorecard.submitted_at + timedelta(hours=float(settings.MOTM_VOTE_WINDOW_HOURS))


def motm_voting_open(scorecard: Scorecard) -> bool:
    if scorecard.motm_closed_at is not None or scorecard.submitted_at is None:
        return False
    closes = motm_window_closes_at(scorecard)
    return closes is not None and now() < closes


@transaction.atomic
def cast_motm_vote(*, match: Match, voter, nominee) -> MotmVote:
    """One vote per roster player, never for themselves (DOMAIN §7)."""
    # Read fresh rather than through the instance's cached reverse relation: callers
    # routinely hold a `match` fetched before the scorecard was submitted, and a stale
    # `submitted_at` would wrongly report voting as closed.
    scorecard = Scorecard.objects.filter(match=match).first()
    if scorecard is None or scorecard.submitted_at is None:
        raise ValidationError({"match": "Voting opens when the scorecard is submitted."})
    if not motm_voting_open(scorecard):
        raise ValidationError({"match": "Voting has closed."})
    if voter.id == nominee.id:
        raise ValidationError({"nominee": "You cannot vote for yourself."})

    roster = set(match.players.values_list("player_id", flat=True))
    if voter.id not in roster:
        raise ValidationError({"voter": "Only players in the match can vote."})
    if nominee.id not in roster:
        raise ValidationError({"nominee": "You can only vote for somebody who played."})

    vote, _ = MotmVote.objects.update_or_create(
        match=match, voter=voter, defaults={"nominee": nominee}
    )
    return vote


def _stat_contribution(scorecard: Scorecard, player_id) -> Decimal:
    """A player's positive-stat total, used to break a MOTM tie (DOMAIN §7)."""
    return sum(
        (
            row.value
            for row in scorecard.player_stats.select_related("stat_definition")
            if row.player_id == player_id and row.stat_definition.is_positive
        ),
        Decimal(0),
    )


@transaction.atomic
def close_motm_voting(*, scorecard: Scorecard, decided_by=None) -> Scorecard:
    """Settle the award. Tie → higher stat contribution → the scorer decides (DOMAIN §7)."""
    if scorecard.motm_closed_at is not None:
        return scorecard

    counts = Counter(
        MotmVote.objects.filter(match=scorecard.match).values_list("nominee_id", flat=True)
    )
    winner_id = None
    if counts:
        top = max(counts.values())
        tied = [player_id for player_id, votes in counts.items() if votes == top]
        if len(tied) == 1:
            winner_id = tied[0]
        else:
            # Tie-break on stats; still tied means the scorer's call, and absent a
            # decision the award simply goes unmade rather than being arbitrary.
            ranked = sorted(tied, key=lambda pid: -_stat_contribution(scorecard, pid))
            best = _stat_contribution(scorecard, ranked[0])
            still_tied = [pid for pid in ranked if _stat_contribution(scorecard, pid) == best]
            if len(still_tied) == 1:
                winner_id = still_tied[0]
            elif decided_by is not None and decided_by.id in still_tied:
                winner_id = decided_by.id

    scorecard.motm_id = winner_id
    scorecard.motm_closed_at = now()
    scorecard.save(update_fields=["motm", "motm_closed_at", "updated_at"])

    if winner_id:
        notify(
            user=scorecard.motm,
            kind=NotificationKind.MOTM_AWARDED,
            url=f"/matches/{scorecard.match_id}/scorecard",
            data={"match_id": str(scorecard.match_id)},
            **_context(scorecard),
        )
    return scorecard


# ---------------------------------------------------------------------------
# Peer ratings (DOMAIN §7)
# ---------------------------------------------------------------------------
@transaction.atomic
def submit_peer_ratings(*, match: Match, rater, ratings: list[dict]) -> list[PeerRating]:
    """Rate other players 1–5 after the match. Anonymous to the recipients.

    Re-submitting replaces the earlier rating rather than adding a second — a player
    changing their mind is normal, stuffing the ballot is not.
    """
    roster = {
        str(entry.player_id): entry.player for entry in match.players.select_related("player")
    }
    if str(rater.id) not in roster:
        raise ValidationError({"rater": "Only players in the match can rate."})

    scorecard = Scorecard.objects.filter(match=match).first()
    if scorecard is None or scorecard.submitted_at is None:
        raise ValidationError({"match": "Rating opens when the scorecard is submitted."})

    limit = int(settings.PEER_RATING_MAX_PER_MATCH)
    if len(ratings) > limit:
        raise ValidationError({"ratings": f"You can rate at most {limit} players."})

    saved = []
    for entry in ratings:
        ratee_id = str(entry.get("player_id"))
        if ratee_id == str(rater.id):
            raise ValidationError({"ratings": "You cannot rate yourself."})
        if ratee_id not in roster:
            raise ValidationError({"ratings": "You can only rate players who were in the match."})

        overall = int(entry.get("overall", 0))
        if not 1 <= overall <= 5:
            raise ValidationError({"ratings": "A rating is between 1 and 5."})

        rating, _ = PeerRating.objects.update_or_create(
            match=match,
            rater=rater,
            ratee=roster[ratee_id],
            defaults={"overall": overall, "skill_taps": entry.get("skill_taps") or []},
        )
        saved.append(rating)

    return saved


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------
def auto_confirm_submitted_scorecards() -> int:
    """DOMAIN §7: no action within 24 hours counts as agreement."""
    deadline = now() - timedelta(hours=float(settings.SCORECARD_AUTO_CONFIRM_HOURS))
    pending = Scorecard.objects.filter(status=ScorecardStatus.SUBMITTED, submitted_at__lte=deadline)
    count = 0
    for scorecard in pending:
        try:
            confirm_scorecard(scorecard=scorecard, actor=None, auto=True)
        except ValidationError:
            continue
        count += 1
    return count


def close_finished_motm_voting() -> int:
    """Close any vote whose window has passed."""
    deadline = now() - timedelta(hours=float(settings.MOTM_VOTE_WINDOW_HOURS))
    due = Scorecard.objects.filter(
        motm_closed_at__isnull=True, submitted_at__isnull=False, submitted_at__lte=deadline
    )
    count = 0
    for scorecard in due:
        close_motm_voting(scorecard=scorecard)
        count += 1
    return count
