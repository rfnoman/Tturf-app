"""Badminton and other racket sports (DOMAIN §7: sets and points)."""

from __future__ import annotations

from .base import ScorecardData, ValidationIssue, number, register

SIDES = ("A", "B")


@register("badminton")
def validate_badminton(data: ScorecardData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # The team score *is* the sets won, so a player's sets_won cannot exceed it.
    for side in SIDES:
        score = data.score(side)
        for player_id, stats in data.player_stats.items():
            if data.player_sides.get(player_id) != side:
                continue
            sets_won = stats.get("sets_won")
            if sets_won is not None and sets_won > score:
                issues.append(
                    ValidationIssue(
                        field="sets_won",
                        message=(
                            f"A player cannot win {number(sets_won)} sets when their side won {score}."
                        ),
                    )
                )

    # A match that ends level is not a badminton result.
    if data.team_a_score == data.team_b_score:
        issues.append(
            ValidationIssue(
                field="team_a_score",
                message="A badminton match cannot end level — somebody wins the decider.",
            )
        )

    return issues
