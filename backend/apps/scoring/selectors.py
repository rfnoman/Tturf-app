"""Read-side queries for scorecards (CLAUDE.md)."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from .models import (
    MatchResult,
    MatchTeam,
    MatchTeamPlayer,
    PlayerStat,
    Scorecard,
    ScorecardEvent,
    ScorecardStatus,
    TeamSide,
)


def _with_related(queryset: QuerySet[Scorecard]) -> QuerySet[Scorecard]:
    return queryset.select_related(
        "match",
        "match__booking",
        "match__booking__ground",
        "match__booking__ground__turf",
        "match__sport",
        "scorer",
        "motm",
        "motm__player_profile",
    ).prefetch_related(
        Prefetch(
            "match__teams",
            queryset=MatchTeam.objects.select_related("captain").prefetch_related(
                Prefetch(
                    "players",
                    queryset=MatchTeamPlayer.objects.select_related(
                        "match_player__player", "match_player__player__player_profile"
                    ),
                )
            ),
        ),
        Prefetch(
            "player_stats",
            queryset=PlayerStat.objects.select_related(
                "stat_definition", "player", "player__player_profile"
            ),
        ),
    )


def scorecard_queryset() -> QuerySet[Scorecard]:
    return _with_related(Scorecard.objects.all()).prefetch_related(
        Prefetch("events", queryset=ScorecardEvent.objects.select_related("actor"))
    )


def public_scorecard_queryset() -> QuerySet[Scorecard]:
    """Locked scorecards only — a shared link must never show an unsettled result."""
    return _with_related(Scorecard.objects.filter(status=ScorecardStatus.LOCKED))


def player_results(user, *, limit: int = 20) -> list[dict]:
    """A player's recent locked results, from their own side's point of view.

    "Won 3–1" means nothing without knowing which side they were on, so the outcome is
    resolved per player rather than left for the client to work out.
    """
    sides = {
        entry.team.match_id: entry.team.side
        for entry in MatchTeamPlayer.objects.filter(match_player__player=user).select_related(
            "team"
        )
    }

    scorecards = (
        public_scorecard_queryset()
        .filter(match__players__player=user)
        .order_by("-match__booking__time_range")
        .distinct()[:limit]
    )

    rows = []
    for scorecard in scorecards:
        side = sides.get(scorecard.match_id, "")
        if not side or not scorecard.result:
            outcome = "unknown"
        elif scorecard.result == MatchResult.DRAW:
            outcome = "draw"
        elif (scorecard.result == MatchResult.TEAM_A and side == TeamSide.A) or (
            scorecard.result == MatchResult.TEAM_B and side == TeamSide.B
        ):
            outcome = "win"
        else:
            outcome = "loss"

        rows.append(
            {
                "match_id": scorecard.match_id,
                "scorecard_id": scorecard.id,
                "sport": scorecard.match.sport.display_name,
                "turf_name": scorecard.match.booking.ground.turf.name,
                "played_at": scorecard.match.starts_at,
                "team_a_score": scorecard.team_a_score,
                "team_b_score": scorecard.team_b_score,
                "result": scorecard.result,
                "my_side": side,
                "outcome": outcome,
                "is_motm": scorecard.motm_id == user.id,
                "verified_by_staff": scorecard.verified_by_staff,
            }
        )
    return rows
