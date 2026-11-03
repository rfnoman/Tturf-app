"""Football and futsal (DOMAIN §7: "sum of player goals per team ≤ team score")."""

from __future__ import annotations

from decimal import Decimal

from .base import ScorecardData, ValidationIssue, number, register

SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}


def _validate(data: ScorecardData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for side in SIDES:
        goals = data.total("goals", side)
        score = data.score(side)
        # Less-than is fine and common: own goals, and a scorer who only filled in the
        # score. More than the team scored is always an error.
        if goals > score:
            issues.append(
                ValidationIssue(
                    field="goals",
                    message=(
                        f"Team {side}'s players have {number(goals)} goals between them, but the "
                        f"team scored {score}."
                    ),
                )
            )

        assists = data.total("assists", side)
        if assists > score:
            issues.append(
                ValidationIssue(
                    field="assists",
                    message=f"Team {side} cannot have more assists ({number(assists)}) than goals ({score}).",
                )
            )

        # A clean sheet means the *other* side did not score.
        clean_sheets = data.total("clean_sheet", side)
        if clean_sheets > 0 and data.score(OTHER[side]) > 0:
            issues.append(
                ValidationIssue(
                    field="clean_sheet",
                    message=(
                        f"Team {side} cannot have a clean sheet: team {OTHER[side]} scored "
                        f"{data.score(OTHER[side])}."
                    ),
                )
            )

    for player_id, stats in data.player_stats.items():
        if stats.get("red", Decimal(0)) > 0 and stats.get("yellow", Decimal(0)) > 2:
            issues.append(
                ValidationIssue(
                    field="yellow",
                    message="A player cannot take more than two yellows before the red.",
                )
            )
        del player_id

    return issues


register("football")(_validate)
register("futsal")(_validate)
