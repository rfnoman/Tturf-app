"""Cricket (DOMAIN §7: "cricket runs/wickets reconcile with team totals")."""

from __future__ import annotations

from decimal import Decimal

from .base import ScorecardData, ValidationIssue, number, register

SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
#: A side cannot lose more wickets than it has batters; box cricket plays 8 a side.
MAX_WICKETS_MARGIN = 1


@register("cricket")
def validate_cricket(data: ScorecardData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for side in SIDES:
        runs = data.total("runs", side)
        score = data.score(side)
        # Extras (wides, byes) are team runs nobody is credited with, so the batters'
        # total can be lower. Higher is impossible.
        if runs > score:
            issues.append(
                ValidationIssue(
                    field="runs",
                    message=(
                        f"Team {side}'s batters made {number(runs)} runs, but the team total is "
                        f"{score}. Check the totals."
                    ),
                )
            )

        # Wickets taken by one side are batters dismissed in the other.
        wickets = data.total("wickets", side)
        batters = sum(1 for pid, s in data.player_sides.items() if s == OTHER[side] and pid)
        if batters and wickets > batters - MAX_WICKETS_MARGIN:
            issues.append(
                ValidationIssue(
                    field="wickets",
                    message=(
                        f"Team {side} cannot take {number(wickets)} wickets against {batters} batters."
                    ),
                )
            )

        conceded = data.total("runs_conceded", side)
        if conceded > data.score(OTHER[side]):
            issues.append(
                ValidationIssue(
                    field="runs_conceded",
                    message=(
                        f"Team {side}'s bowlers conceded {number(conceded)}, but team "
                        f"{OTHER[side]} only made {data.score(OTHER[side])}."
                    ),
                )
            )

    for stats in data.player_stats.values():
        runs = stats.get("runs", Decimal(0))
        balls = stats.get("balls", Decimal(0))
        # You cannot score off balls you did not face. Boundaries mean runs can exceed
        # balls, so only the zero-balls case is checkable.
        if runs > 0 and balls == 0:
            issues.append(
                ValidationIssue(
                    field="balls",
                    message="A batter with runs must have faced at least one ball.",
                )
            )

    return issues
