"""Per-sport scorecard validation (DOMAIN §7, phase 05 step 6).

Pure unit tests against made-up numbers: the validators take a value object precisely so
they can be exercised without building a match, and so the rules read as rules.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.scoring.validators.base import (
    ScorecardData,
    ValidationIssue,
    generic_validator,
    registered_sports,
    validate_scorecard,
)
from apps.sports.models import StatDefinition

pytestmark = pytest.mark.django_db


def definitions_for(sport_slug: str) -> dict[str, StatDefinition]:
    return {
        definition.key: definition
        for definition in StatDefinition.objects.filter(sport__slug=sport_slug)
    }


def build(
    sport_slug: str,
    *,
    a: int = 0,
    b: int = 0,
    players: dict | None = None,
    sides: dict | None = None,
) -> ScorecardData:
    """A scorecard for ``sport_slug``; player keys are simple strings."""
    return ScorecardData(
        sport_slug=sport_slug,
        team_a_score=a,
        team_b_score=b,
        player_stats={
            key: {stat: Decimal(str(value)) for stat, value in stats.items()}
            for key, stats in (players or {}).items()
        },
        player_sides=sides or {},
        definitions=definitions_for(sport_slug),
    )


def fields(issues: list[ValidationIssue]) -> set[str]:
    return {issue.field for issue in issues}


class TestGeneric:
    def test_a_clean_card_has_no_issues(self):
        data = build(
            "football",
            a=2,
            b=1,
            players={"p1": {"goals": 2}, "p2": {"goals": 1}},
            sides={"p1": "A", "p2": "B"},
        )
        assert generic_validator(data) == []

    def test_a_value_above_the_maximum_is_caught(self):
        data = build("football", a=1, b=0, players={"p1": {"yellow": 9}}, sides={"p1": "A"})
        assert "yellow" in fields(generic_validator(data))

    def test_a_negative_value_is_caught(self):
        data = build("football", a=1, b=0, players={"p1": {"goals": -1}}, sides={"p1": "A"})
        assert "goals" in fields(generic_validator(data))

    def test_a_fractional_value_for_a_whole_number_stat_is_caught(self):
        data = build("football", a=1, b=0, players={"p1": {"goals": 1.5}}, sides={"p1": "A"})
        assert "goals" in fields(generic_validator(data))

    def test_a_decimal_stat_accepts_fractions(self):
        """Cricket overs are 4.3 — three balls into the fifth over."""
        data = build("cricket", a=40, b=30, players={"p1": {"overs": 4.3}}, sides={"p1": "A"})
        assert "overs" not in fields(generic_validator(data))

    def test_a_stat_the_sport_does_not_have_is_caught(self):
        data = build("football", a=1, b=0, players={"p1": {"wickets": 3}}, sides={"p1": "A"})
        assert "wickets" in fields(generic_validator(data))

    def test_a_player_with_no_team_is_caught(self):
        data = build("football", a=1, b=0, players={"ghost": {"goals": 1}}, sides={})
        assert "players" in fields(generic_validator(data))


class TestFootball:
    def test_goals_adding_up_is_accepted(self):
        data = build(
            "football",
            a=3,
            b=1,
            players={"p1": {"goals": 2}, "p2": {"goals": 1}, "p3": {"goals": 1}},
            sides={"p1": "A", "p2": "A", "p3": "B"},
        )
        assert validate_scorecard(data) == []

    def test_more_player_goals_than_the_team_score_is_rejected(self):
        """Acceptance: goals that exceed the team score are rejected."""
        data = build(
            "football",
            a=2,
            b=0,
            players={"p1": {"goals": 2}, "p2": {"goals": 1}},
            sides={"p1": "A", "p2": "A"},
        )
        issues = validate_scorecard(data)
        assert "goals" in fields(issues)
        assert "3 goals between them" in issues[0].message

    def test_fewer_player_goals_than_the_score_is_fine(self):
        """Own goals, and a scorer who only filled in the score."""
        data = build("football", a=3, b=0, players={"p1": {"goals": 1}}, sides={"p1": "A"})
        assert validate_scorecard(data) == []

    def test_more_assists_than_goals_is_rejected(self):
        data = build(
            "football",
            a=1,
            b=0,
            players={"p1": {"assists": 2}},
            sides={"p1": "A"},
        )
        assert "assists" in fields(validate_scorecard(data))

    def test_a_clean_sheet_against_a_side_that_scored_is_rejected(self):
        data = build(
            "football",
            a=2,
            b=1,
            players={"p1": {"clean_sheet": 1}},
            sides={"p1": "A"},
        )
        assert "clean_sheet" in fields(validate_scorecard(data))

    def test_a_genuine_clean_sheet_is_accepted(self):
        data = build(
            "football",
            a=2,
            b=0,
            players={"p1": {"clean_sheet": 1}},
            sides={"p1": "A"},
        )
        assert validate_scorecard(data) == []

    def test_futsal_uses_the_same_rules(self):
        data = build("futsal", a=1, b=0, players={"p1": {"goals": 5}}, sides={"p1": "A"})
        assert "goals" in fields(validate_scorecard(data))


class TestCricket:
    def test_runs_reconciling_is_accepted(self):
        data = build(
            "cricket",
            a=120,
            b=98,
            players={"p1": {"runs": 60, "balls": 40}, "p2": {"runs": 55, "balls": 38}},
            sides={"p1": "A", "p2": "A", "p3": "B"},
        )
        assert validate_scorecard(data) == []

    def test_more_batter_runs_than_the_team_total_is_rejected(self):
        data = build(
            "cricket",
            a=100,
            b=90,
            players={"p1": {"runs": 60, "balls": 40}, "p2": {"runs": 55, "balls": 38}},
            sides={"p1": "A", "p2": "A"},
        )
        assert "runs" in fields(validate_scorecard(data))

    def test_extras_mean_batter_runs_can_be_lower(self):
        data = build(
            "cricket",
            a=120,
            b=90,
            players={"p1": {"runs": 100, "balls": 60}},
            sides={"p1": "A"},
        )
        assert validate_scorecard(data) == []

    def test_more_wickets_than_batters_is_rejected(self):
        data = build(
            "cricket",
            a=100,
            b=90,
            players={"p1": {"wickets": 5}},
            sides={"p1": "A", "p2": "B", "p3": "B"},
        )
        assert "wickets" in fields(validate_scorecard(data))

    def test_conceding_more_than_the_other_side_made_is_rejected(self):
        data = build(
            "cricket",
            a=100,
            b=50,
            players={"p1": {"runs_conceded": 80}},
            sides={"p1": "A"},
        )
        assert "runs_conceded" in fields(validate_scorecard(data))

    def test_runs_without_facing_a_ball_is_rejected(self):
        data = build(
            "cricket", a=30, b=20, players={"p1": {"runs": 30, "balls": 0}}, sides={"p1": "A"}
        )
        assert "balls" in fields(validate_scorecard(data))

    def test_boundaries_mean_runs_can_exceed_balls(self):
        data = build(
            "cricket", a=30, b=20, players={"p1": {"runs": 24, "balls": 6}}, sides={"p1": "A"}
        )
        assert validate_scorecard(data) == []


class TestBadminton:
    def test_a_normal_result_is_accepted(self):
        data = build(
            "badminton",
            a=2,
            b=1,
            players={"p1": {"sets_won": 2}, "p2": {"sets_won": 1}},
            sides={"p1": "A", "p2": "B"},
        )
        assert validate_scorecard(data) == []

    def test_a_draw_is_rejected(self):
        data = build("badminton", a=1, b=1, sides={"p1": "A", "p2": "B"})
        assert "team_a_score" in fields(validate_scorecard(data))

    def test_a_player_winning_more_sets_than_their_side_is_rejected(self):
        data = build(
            "badminton",
            a=2,
            b=1,
            players={"p1": {"sets_won": 3}},
            sides={"p1": "A", "p2": "B"},
        )
        assert "sets_won" in fields(validate_scorecard(data))


def test_an_unknown_sport_gets_the_generic_validator_only():
    """Owners can propose sports this codebase has never heard of (DOMAIN §2)."""
    data = ScorecardData(
        sport_slug="kabaddi",
        team_a_score=30,
        team_b_score=28,
        player_stats={},
        player_sides={"p1": "A"},
        definitions={},
    )
    # No rules to apply, and crucially no crash.
    assert validate_scorecard(data) == []


def test_the_sports_with_their_own_rules_are_registered():
    assert set(registered_sports()) == {"football", "futsal", "cricket", "badminton"}
