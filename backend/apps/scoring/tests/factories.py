"""Scoring test setup: a played match with teams, ready to score."""

from __future__ import annotations

from datetime import timedelta

from psycopg.types.range import TimestamptzRange

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import Booking
from apps.core.utils import now
from apps.matches.models import MatchPlayer, MatchStatus
from apps.matches.services import add_player
from apps.matches.tests.factories import make_match
from apps.players.services import complete_onboarding
from apps.scoring.models import TeamSide
from apps.scoring.services import get_or_create_scorecard, set_captain, set_teams


def onboard(user, sport: str = "football", skill: int = 60):
    """A profile with a rating, so auto-balance has something to balance on."""
    return complete_onboarding(
        user=user,
        data={
            "attributes": {"stamina": skill, "agility": skill, "speed": skill, "strength": skill},
            "sports": [{"sport": sport, "positions": [], "skills": {}}],
        },
    )


def played_match(
    *,
    organiser=None,
    players: int = 4,
    sport: str = "football",
    fmt: str = "5v5",
    finished: bool = True,
):
    """A match in the past with ``players`` on the roster.

    The slot is backdated so the match is genuinely over — scoring a game that has not
    kicked off yet is not a case the product has.
    """
    organiser = organiser or UserFactory()
    match = make_match(booker=organiser, sport=sport, fmt=fmt, max_players=max(2, players))

    for _ in range(players - 1):
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)

    if finished:
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(hours=3), now() - timedelta(hours=2))
        )
        match.status = MatchStatus.FINISHED
        match.save(update_fields=["status"])
        match.refresh_from_db()

    return match


def split_teams(match, *, actor=None, captains: bool = True):
    """Put the roster on two sides, alternating, and name both captains."""
    actor = actor or match.organiser
    roster = list(match.players.order_by("created_at"))
    assignments = {
        str(entry.id): TeamSide.A if index % 2 == 0 else TeamSide.B
        for index, entry in enumerate(roster)
    }
    teams = set_teams(match=match, assignments=assignments, actor=actor)

    if captains:
        for team in teams:
            first = team.players.first()
            if first is not None:
                set_captain(match=match, side=team.side, player=first.player, actor=actor)

    return {team.side: team for team in match.teams.order_by("side")}


def ready_to_score(*, players: int = 4, sport: str = "football", fmt: str = "5v5"):
    """A finished match with teams, captains and a draft scorecard."""
    match = played_match(players=players, sport=sport, fmt=fmt)
    teams = split_teams(match)
    scorecard = get_or_create_scorecard(match=match)
    return match, teams, scorecard
