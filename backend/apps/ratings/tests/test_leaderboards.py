"""The nightly boards (DOMAIN §8)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest

from apps.ratings.models import LeaderboardEntry, RatingChange
from apps.ratings.selectors import leaderboard, period_start
from apps.ratings.tasks import rebuild_leaderboards
from apps.scoring.models import TeamSide
from apps.sports.models import Sport

from .factories import locked_match

pytestmark = pytest.mark.django_db


def football():
    return Sport.objects.get(slug="football")


class TestRebuild:
    def test_a_board_ranks_the_players_who_played(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 3}}, scores=(3, 0))
        turf = match.booking.ground.turf

        rebuild_leaderboards()

        rows = list(leaderboard(sport=football(), turf=turf, metric=LeaderboardEntry.Metric.WINS))
        assert rows
        assert rows[0].rank == 1
        assert rows[0].value == Decimal("1")

    def test_the_top_scorer_board_uses_the_sport_headline_stat(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 3}}, scores=(3, 0))
        scorer = teams[TeamSide.A].players.first().match_player.player.player_profile

        rebuild_leaderboards()

        rows = list(
            leaderboard(
                sport=football(),
                turf=match.booking.ground.turf,
                metric=LeaderboardEntry.Metric.TOP_STAT,
                stat_key="goals",
            )
        )
        assert rows[0].profile == scorer
        assert rows[0].value == Decimal("3")

    def test_a_platform_wide_board_exists_alongside_the_turf_one(self):
        locked_match(scores=(2, 0))
        rebuild_leaderboards()

        assert leaderboard(sport=football(), turf=None, metric=LeaderboardEntry.Metric.WINS)

    def test_last_months_match_is_not_on_this_months_board(self):
        match, _teams, _ = locked_match(scores=(2, 0))
        last_month = datetime.combine(
            period_start(LeaderboardEntry.Period.MONTH) - timedelta(days=1),
            time(12, 0),
            tzinfo=UTC,
        )
        RatingChange.objects.filter(match=match).update(played_at=last_month)

        rebuild_leaderboards()

        monthly = leaderboard(
            sport=football(),
            turf=match.booking.ground.turf,
            metric=LeaderboardEntry.Metric.WINS,
            period=LeaderboardEntry.Period.MONTH,
        )
        all_time = leaderboard(
            sport=football(),
            turf=match.booking.ground.turf,
            metric=LeaderboardEntry.Metric.WINS,
            period=LeaderboardEntry.Period.ALL_TIME,
        )
        assert list(monthly) == []
        assert list(all_time)

    def test_rebuilding_twice_does_not_double_the_rows(self):
        locked_match(scores=(2, 0))
        rebuild_leaderboards()
        first = LeaderboardEntry.objects.count()
        rebuild_leaderboards()

        assert LeaderboardEntry.objects.count() == first

    def test_a_board_is_capped(self):
        from django.conf import settings

        locked_match(players=4, scores=(2, 0))
        rebuild_leaderboards()

        for entry in LeaderboardEntry.objects.values("sport", "turf", "metric", "period"):
            count = LeaderboardEntry.objects.filter(**entry).count()
            assert count <= int(settings.LEADERBOARD_SIZE)

    def test_nothing_to_rank_is_not_an_error(self):
        assert rebuild_leaderboards() == 0
