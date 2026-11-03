"""What a locked scorecard does to a profile (DOMAIN §3 and §8)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.players.models import PlayerSkill, PlayerSport, PlayerSportRating, RatingSource
from apps.ratings.models import (
    ConductReport,
    PlayerGroundStats,
    PlayerSportStats,
    RatingChange,
)
from apps.ratings.services import (
    apply_locked_scorecard,
    fair_play,
    recompute_all,
    report_conduct,
    review_conduct,
)
from apps.scoring.models import TeamSide

from .factories import locked_match

pytestmark = pytest.mark.django_db


def winner_profile(teams, side=TeamSide.A):
    return teams[side].players.first().match_player.player.player_profile


class TestApplyLockedScorecard:
    def test_locking_a_card_rates_everybody_who_played(self):
        """The hook does this by itself; the test calls it directly to be explicit."""
        match, teams, scorecard = locked_match()

        assert RatingChange.objects.filter(match=match).count() == 4
        for change in RatingChange.objects.filter(match=match):
            assert change.before_overall != 0
            assert change.breakdown["result"] in {"win", "loss", "draw"}

    def test_the_winners_go_up_and_the_losers_come_down(self):
        _match, teams, _scorecard = locked_match(scores=(3, 0))

        won = RatingChange.objects.get(profile=winner_profile(teams, TeamSide.A))
        lost = RatingChange.objects.get(profile=winner_profile(teams, TeamSide.B))
        assert won.delta > lost.delta

    def test_a_goalscorer_gains_more_than_a_teammate_who_did_nothing(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 3}}, scores=(3, 0))

        scorer = teams[TeamSide.A].players.first().match_player.player.player_profile
        others = [
            entry.match_player.player.player_profile
            for entry in teams[TeamSide.A].players.all()[1:]
        ]
        scorer_change = RatingChange.objects.get(profile=scorer, match=match)
        for other in others:
            assert scorer_change.delta > RatingChange.objects.get(profile=other, match=match).delta

    def test_goals_move_finishing_and_mark_it_computed(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 3}}, scores=(3, 0))
        profile = winner_profile(teams)

        finishing = PlayerSkill.objects.get(
            profile=profile, sport_skill__key="finishing", sport_skill__sport=match.sport
        )
        assert finishing.source == RatingSource.COMPUTED
        assert finishing.value > 50

    def test_the_rating_counters_are_filled_in(self):
        match, teams, _ = locked_match(scores=(3, 1))
        rating = PlayerSportRating.objects.get(profile=winner_profile(teams), sport=match.sport)

        assert rating.matches_counted == 1
        assert rating.matches_played == 1
        assert rating.wins == 1
        assert rating.last_match_at is not None

    def test_playing_verifies_the_sport(self):
        match, teams, _ = locked_match()
        player_sport = PlayerSport.objects.get(profile=winner_profile(teams), sport=match.sport)
        assert player_sport.is_verified is True

    def test_attendance_is_filled_in_from_the_card(self):
        match, _teams, _ = locked_match()
        assert set(match.players.values_list("attended", flat=True)) == {True}

    def test_applying_the_same_card_twice_changes_nothing(self):
        """The hook can fire again — a retried task, a replayed lock."""
        _match, teams, scorecard = locked_match(scores=(2, 0))
        profile = winner_profile(teams)
        after_first = PlayerSportRating.objects.get(profile=profile).overall

        apply_locked_scorecard(scorecard=scorecard)

        assert PlayerSportRating.objects.get(profile=profile).overall == after_first
        assert RatingChange.objects.filter(profile=profile).count() == 1

    def test_a_card_that_is_not_locked_is_ignored(self):
        from apps.scoring.tests.factories import ready_to_score

        _match, _teams, scorecard = ready_to_score()
        assert apply_locked_scorecard(scorecard=scorecard) == []

    def test_a_verified_card_moves_ratings_further(self):
        # A narrow win with nothing else in it: a hat-trick would hit the clamp in both
        # cases and the multiplier would be invisible.
        plain = locked_match(scores=(1, 0))
        verified = locked_match(scores=(1, 0), verified=True)

        plain_delta = RatingChange.objects.get(profile=winner_profile(plain[1])).delta
        verified_delta = RatingChange.objects.get(profile=winner_profile(verified[1])).delta
        assert verified_delta > plain_delta

    def test_the_breakdown_is_stored_with_the_inputs(self):
        _match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        change = RatingChange.objects.get(profile=winner_profile(teams))

        assert change.inputs["result"] == "win"
        assert change.inputs["stats"]["goals"] == "2"
        assert "components" in change.breakdown
        assert change.weights_version >= 1


class TestTrackRecord:
    def test_totals_are_kept_per_sport(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        totals = PlayerSportStats.objects.get(profile=winner_profile(teams), sport=match.sport)

        assert totals.matches == 1
        assert totals.wins == 1
        assert totals.stat_totals["goals"] == "2"
        assert totals.recent_results == ["win"]

    def test_totals_are_kept_per_ground(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 1}}, scores=(1, 0))
        ground_stats = PlayerGroundStats.objects.get(
            profile=winner_profile(teams), ground=match.booking.ground
        )

        assert ground_stats.matches == 1
        assert ground_stats.turf == match.booking.ground.turf
        assert ground_stats.stat_totals["goals"] == "1"

    def test_minutes_are_not_totalled_as_an_achievement(self):
        match, teams, _ = locked_match(
            stats={TeamSide.A: {"goals": 1, "minutes_played": 60}}, scores=(1, 0)
        )
        totals = PlayerSportStats.objects.get(profile=winner_profile(teams), sport=match.sport)
        assert "minutes_played" not in totals.stat_totals

    def test_the_form_guide_keeps_only_the_last_five(self):
        from apps.ratings.services import FORM_LENGTH, push_form

        form: list[str] = []
        for outcome in ["win", "loss", "draw", "win", "win", "loss", "win"]:
            form = push_form(form, outcome)

        assert len(form) == FORM_LENGTH
        # Most recent first, so the newest result is what a reader sees first.
        assert form == ["win", "loss", "win", "win", "draw"]


class TestRecompute:
    def test_a_replay_lands_on_the_same_rating(self):
        """DOMAIN §8: the engine is deterministic, so history can be replayed."""
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        profile = winner_profile(teams)
        incremental = PlayerSportRating.objects.get(profile=profile, sport=match.sport)
        before = (incremental.overall, incremental.matches_counted, incremental.wins)

        replayed = recompute_all(profile=profile, sport=match.sport)

        assert (replayed.overall, replayed.matches_counted, replayed.wins) == before

    def test_a_replay_with_no_matches_falls_back_to_the_self_assessment(self):
        match, teams, _ = locked_match()
        profile = winner_profile(teams)
        RatingChange.objects.filter(profile=profile).delete()

        rating = recompute_all(profile=profile, sport=match.sport)

        assert rating.matches_counted == 0
        assert rating.is_provisional is True


class TestConduct:
    def test_a_player_can_report_another(self):
        match, teams, _ = locked_match()
        roster = list(match.players.select_related("player"))

        report = report_conduct(
            match=match,
            reporter=roster[0].player,
            reported=roster[1].player,
            reason=ConductReport.Reason.ABUSIVE,
            details="Swore at the referee all game",
        )
        assert report.status == ConductReport.Status.OPEN

    def test_nobody_can_report_themselves(self):
        match, _teams, _ = locked_match()
        player = match.players.first().player

        with pytest.raises(Exception, match="yourself"):
            report_conduct(
                match=match, reporter=player, reported=player, reason=ConductReport.Reason.OTHER
            )

    def test_only_players_in_the_match_can_report(self):
        from apps.accounts.tests.factories import UserFactory

        match, _teams, _ = locked_match()
        outsider = UserFactory()

        with pytest.raises(Exception, match="Only players"):
            report_conduct(
                match=match,
                reporter=outsider,
                reported=match.players.first().player,
                reason=ConductReport.Reason.OTHER,
            )

    def test_the_same_person_cannot_be_reported_twice_for_one_match(self):
        match, _teams, _ = locked_match()
        roster = list(match.players.select_related("player"))
        report_conduct(
            match=match,
            reporter=roster[0].player,
            reported=roster[1].player,
            reason=ConductReport.Reason.OTHER,
        )

        with pytest.raises(Exception, match="already reported"):
            report_conduct(
                match=match,
                reporter=roster[0].player,
                reported=roster[1].player,
                reason=ConductReport.Reason.ABUSIVE,
            )

    def test_only_an_admin_reviews(self):
        match, _teams, _ = locked_match()
        roster = list(match.players.select_related("player"))
        report = report_conduct(
            match=match,
            reporter=roster[0].player,
            reported=roster[1].player,
            reason=ConductReport.Reason.OTHER,
        )

        with pytest.raises(Exception, match="platform admin"):
            review_conduct(report=report, reviewer=roster[0].player, uphold=True)

    def test_a_reviewed_report_cannot_be_reviewed_again(self):
        from apps.accounts.tests.factories import UserFactory

        match, _teams, _ = locked_match()
        roster = list(match.players.select_related("player"))
        admin = UserFactory(is_platform_admin=True)
        report = report_conduct(
            match=match,
            reporter=roster[0].player,
            reported=roster[1].player,
            reason=ConductReport.Reason.OTHER,
        )
        review_conduct(report=report, reviewer=admin, uphold=True)

        with pytest.raises(Exception, match="already been reviewed"):
            review_conduct(report=report, reviewer=admin, uphold=False)


class TestFairPlay:
    def test_a_clean_record_is_a_hundred(self):
        _match, teams, _ = locked_match()
        assert fair_play(profile=winner_profile(teams)) == {
            "score": 100,
            "band": "good",
            "yellow_cards": 0,
            "red_cards": 0,
            "upheld_reports": 0,
        }

    def test_cards_cost_points(self):
        _match, teams, _ = locked_match(
            stats={TeamSide.A: {"goals": 1, "yellow": 1, "red": 1}}, scores=(1, 0)
        )
        result = fair_play(profile=winner_profile(teams))

        assert result["yellow_cards"] == 1
        assert result["red_cards"] == 1
        assert result["score"] == 90

    def test_an_open_report_changes_nothing_until_it_is_upheld(self):
        from apps.accounts.tests.factories import UserFactory

        match, teams, _ = locked_match()
        roster = list(match.players.select_related("player"))
        reported_profile = roster[1].player.player_profile

        report = report_conduct(
            match=match,
            reporter=roster[0].player,
            reported=roster[1].player,
            reason=ConductReport.Reason.ABUSIVE,
        )
        assert fair_play(profile=reported_profile)["score"] == 100

        review_conduct(report=report, reviewer=UserFactory(is_platform_admin=True), uphold=True)
        assert fair_play(profile=reported_profile)["score"] == 85
        assert fair_play(profile=reported_profile)["band"] == "good"

    def test_a_bad_record_lands_in_the_poor_band(self):
        from apps.accounts.tests.factories import UserFactory

        match, _teams, _ = locked_match()
        roster = list(match.players.select_related("player"))
        admin = UserFactory(is_platform_admin=True)
        reported = roster[1].player

        for reporter in roster[:3]:
            if reporter.player_id == reported.id:
                continue
            report = report_conduct(
                match=match,
                reporter=reporter.player,
                reported=reported,
                reason=ConductReport.Reason.ABUSIVE,
            )
            review_conduct(report=report, reviewer=admin, uphold=True)

        assert fair_play(profile=reported.player_profile)["band"] in {"warning", "poor"}


def test_a_decimal_stat_total_is_kept_exactly():
    """Cricket overs are decimal; a float here would drift."""
    # The cricket validator reconciles runs with the team total, so the scoreline has
    # to be a real one.
    _match, teams, _ = locked_match(
        sport="cricket",
        fmt="box",
        stats={TeamSide.A: {"runs": 45, "balls": 30}},
        scores=(45, 20),
    )
    totals = PlayerSportStats.objects.get(profile=winner_profile(teams))
    assert Decimal(totals.stat_totals["runs"]) == Decimal("45")
