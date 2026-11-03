"""Golden values for the rating engine (DOMAIN §8).

The engine is pure, so these tests are arithmetic with no database behind them. They are
written as *scenarios a person can argue with* — "a hat-trick in a win should move a new
player up a lot, and the same hat-trick should move a settled player up a little" — with
the resulting numbers pinned so a change to the weights has to be deliberate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.ratings.engine import (
    MatchPerformance,
    match_performance_score,
    rate_match,
)
from apps.ratings.weights import WEIGHTS_VERSION


def football(**overrides) -> MatchPerformance:
    base = {
        "sport_slug": "football",
        "stats": {},
        "result": "draw",
        "current_overall": 50,
        "current_skills": {"finishing": 50, "passing": 50, "defending": 50, "goalkeeping": 50},
        "current_attributes": {"stamina": 50, "speed": 50, "agility": 50, "strength": 50},
        "matches_counted": 30,
    }
    return MatchPerformance(**{**base, **overrides})


class TestPerformanceScore:
    def test_a_quiet_match_is_not_a_bad_match(self):
        """No goals, no assists, drew: a defender's ordinary Tuesday."""
        scored = match_performance_score(football())
        assert scored["components"]["stats"] == Decimal("40")
        assert scored["components"]["result"] == Decimal("60")
        # 40×0.45 + 60×0.35 over 0.80
        assert scored["score"] == Decimal("48.75")

    def test_goals_and_a_win_score_well(self):
        scored = match_performance_score(
            football(stats={"goals": Decimal("2"), "assists": Decimal("1")}, result="win")
        )
        assert scored["score"] > Decimal("70")

    def test_one_stat_cannot_carry_the_whole_score(self):
        """Ten goals is capped at 1.5× the benchmark, so it is not a free 99."""
        modest = match_performance_score(football(stats={"goals": Decimal("2")}))
        absurd = match_performance_score(football(stats={"goals": Decimal("10")}))
        assert absurd["score"] == modest["score"]

    def test_cards_come_straight_off(self):
        clean = match_performance_score(football(stats={"goals": Decimal("1")}))
        booked = match_performance_score(
            football(stats={"goals": Decimal("1"), "yellow": Decimal("1")})
        )
        assert clean["score"] - booked["score"] == Decimal("5") * Decimal("0.45") / Decimal("0.80")

    def test_beating_a_stronger_side_is_worth_more(self):
        even = match_performance_score(football(result="win", team_average=60, opponent_average=60))
        upset = match_performance_score(
            football(result="win", team_average=60, opponent_average=75)
        )
        assert upset["score"] > even["score"]

    def test_the_opponent_swing_is_capped(self):
        big = match_performance_score(football(result="win", team_average=20, opponent_average=99))
        capped = match_performance_score(
            football(result="win", team_average=60, opponent_average=70)
        )
        assert big["score"] == capped["score"]

    def test_peer_ratings_count_when_there_are_any(self):
        without = match_performance_score(football(result="win"))
        with_peers = match_performance_score(
            football(result="win", peer_average=Decimal("5"), peer_count=3)
        )
        assert with_peers["score"] > without["score"]

    def test_a_match_nobody_rated_is_not_marked_down(self):
        """The peer weight is redistributed, not scored as zero."""
        without = match_performance_score(football(result="win"))
        average_peers = match_performance_score(
            football(result="win", peer_average=Decimal("3"), peer_count=4)
        )
        assert average_peers["score"] < without["score"]
        # 40×0.45 + 85×0.35, over the 0.80 of weight that was actually used.
        assert without["score"] == Decimal("59.6875")

    def test_minutes_scale_the_stats_but_not_the_baseline(self):
        full = match_performance_score(
            football(stats={"goals": Decimal("1")}, minutes=Decimal("60"))
        )
        cameo = match_performance_score(
            football(stats={"goals": Decimal("1")}, minutes=Decimal("15"))
        )
        assert cameo["components"]["stats"] < full["components"]["stats"]
        assert cameo["components"]["stats"] > Decimal("40")

    def test_unrecorded_minutes_mean_a_full_match(self):
        recorded = match_performance_score(
            football(stats={"goals": Decimal("1")}, minutes=Decimal("60"))
        )
        silent = match_performance_score(football(stats={"goals": Decimal("1")}))
        assert recorded["score"] == silent["score"]

    def test_motm_is_a_flat_bonus(self):
        plain = match_performance_score(football(result="win"))
        motm = match_performance_score(football(result="win", is_motm=True))
        assert motm["score"] - plain["score"] == Decimal("6")

    def test_a_sport_with_no_weights_is_still_rated(self):
        """Result and peers need no stat table — that is what makes new sports cheap."""
        scored = match_performance_score(
            MatchPerformance(
                sport_slug="kabaddi", result="win", peer_average=Decimal("4"), peer_count=2
            )
        )
        assert scored["score"] > Decimal("60")


class TestRateMatch:
    def test_a_new_player_moves_faster_than_a_settled_one(self):
        performance = {"stats": {"goals": Decimal("2")}, "result": "win"}
        new = rate_match(football(matches_counted=1, **performance))
        settled = rate_match(football(matches_counted=40, **performance))

        assert new.overall > settled.overall
        assert new.breakdown["provisional"] is True
        assert settled.breakdown["provisional"] is False

    def test_a_settled_rating_never_moves_more_than_three_in_a_match(self):
        """The clamp is the whole defence against one freak scoreline."""
        outcome = rate_match(
            football(
                stats={"goals": Decimal("5"), "assists": Decimal("3")},
                result="win",
                is_motm=True,
                peer_average=Decimal("5"),
                peer_count=8,
                verified=True,
                current_overall=40,
                matches_counted=50,
            )
        )
        assert outcome.overall == 43

    def test_a_provisional_rating_may_move_six(self):
        outcome = rate_match(
            football(
                stats={"goals": Decimal("5")},
                result="win",
                is_motm=True,
                verified=True,
                current_overall=40,
                matches_counted=0,
            )
        )
        assert outcome.overall == 46

    def test_a_verified_card_counts_for_more(self):
        unverified = rate_match(football(stats={"goals": Decimal("1")}, result="win"))
        verified = rate_match(football(stats={"goals": Decimal("1")}, result="win", verified=True))
        assert verified.overall >= unverified.overall
        assert verified.breakdown["verified_multiplier"] == "1.5"

    def test_a_bad_match_moves_the_rating_down(self):
        outcome = rate_match(
            football(result="loss", stats={"red": Decimal("1")}, current_overall=70)
        )
        assert outcome.overall < 70

    def test_goals_move_finishing_and_leave_dribbling_alone(self):
        outcome = rate_match(football(stats={"goals": Decimal("2")}, result="win"))
        assert outcome.skills["finishing"] > 50
        assert "dribbling" not in outcome.skills

    def test_a_skill_the_player_does_not_have_is_not_invented(self):
        outcome = rate_match(
            football(stats={"saves": Decimal("4")}, current_skills={"finishing": 50})
        )
        assert "goalkeeping" not in outcome.skills

    def test_minutes_move_stamina_and_nothing_else(self):
        outcome = rate_match(football(minutes=Decimal("90"), result="win"))
        assert outcome.attributes["stamina"] > 50
        assert set(outcome.attributes) == {"stamina"}

    def test_no_minutes_means_no_attribute_change(self):
        assert rate_match(football(result="win")).attributes == {}

    def test_ratings_stay_inside_the_scale(self):
        top = rate_match(
            football(
                stats={"goals": Decimal("5"), "assists": Decimal("3"), "saves": Decimal("9")},
                result="win",
                is_motm=True,
                peer_average=Decimal("5"),
                peer_count=6,
                verified=True,
                current_overall=95,
                matches_counted=0,
            )
        )
        # The floor is a guard, not something one match can reach: even a red card in a
        # defeat scores about 32, so a player rated 1 still goes *up*.
        bottom = rate_match(
            football(
                result="loss", stats={"red": Decimal("1")}, current_overall=1, matches_counted=0
            )
        )
        assert 95 < top.overall <= 99
        assert bottom.overall >= 1

    def test_a_rating_has_to_be_re_earned(self):
        """A 99 who has an ordinary match comes down, which is the point of an average."""
        outcome = rate_match(football(result="win", current_overall=99, matches_counted=40))
        assert outcome.overall < 99

    def test_the_breakdown_explains_the_change(self):
        outcome = rate_match(football(stats={"goals": Decimal("1")}, result="win", is_motm=True))
        assert outcome.weights_version == WEIGHTS_VERSION
        assert outcome.breakdown["result"] == "win"
        assert outcome.breakdown["motm_bonus"] == "6"
        assert Decimal(outcome.breakdown["overall_delta"]) > 0
        assert set(outcome.breakdown["components"]) == {"stats", "result"}

    def test_the_same_input_always_gives_the_same_output(self):
        """Determinism is what makes recomputing from history meaningful."""
        performance = football(
            stats={"goals": Decimal("1")}, result="win", peer_average=Decimal("4"), peer_count=3
        )
        assert rate_match(performance) == rate_match(performance)


@pytest.mark.parametrize("sport", ["football", "futsal", "cricket", "badminton"])
def test_every_catalogued_sport_scores_a_blank_card_the_same_way(sport):
    """A sport nobody recorded stats for still produces a sane number."""
    scored = match_performance_score(MatchPerformance(sport_slug=sport, result="draw"))
    assert scored["score"] == Decimal("48.75")
