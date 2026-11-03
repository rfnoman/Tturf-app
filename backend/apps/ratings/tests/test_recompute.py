"""Replaying history, and the line between a self-assessment and an earned rating."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.players.models import PlayerSportRating
from apps.players.services import refresh_sport_rating, set_player_skills
from apps.ratings.models import RatingChange
from apps.ratings.services import recompute_all
from apps.scoring.models import TeamSide

from .factories import locked_match

pytestmark = pytest.mark.django_db


def played(side=TeamSide.A):
    match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
    return match, teams[side].players.first().match_player.player.player_profile


class TestRecompute:
    def test_a_replay_reproduces_the_incremental_result(self):
        match, profile = played()
        rating = PlayerSportRating.objects.get(profile=profile, sport=match.sport)
        before = rating.overall

        recompute_all(profile=profile, sport=match.sport)

        rating.refresh_from_db()
        assert rating.overall == before

    def test_a_replay_rewrites_the_stored_explanation(self):
        match, profile = played()
        change = RatingChange.objects.get(profile=profile, match=match)
        change.breakdown = {"stale": True}
        change.save(update_fields=["breakdown"])

        recompute_all(profile=profile, sport=match.sport)

        change.refresh_from_db()
        assert "components" in change.breakdown

    def test_replaying_twice_is_the_same_as_replaying_once(self):
        match, profile = played()
        first = recompute_all(profile=profile, sport=match.sport).overall
        second = recompute_all(profile=profile, sport=match.sport).overall
        assert first == second


class TestEarnedRatingsAreNotClobbered:
    def test_editing_skills_does_not_reset_an_earned_rating(self):
        """DECISIONS D44: the engine owns the overall once a match has been counted."""
        match, profile = played()
        earned = PlayerSportRating.objects.get(profile=profile, sport=match.sport).overall

        set_player_skills(
            profile=profile, sport=match.sport, values={"finishing": 10, "passing": 10}
        )
        refresh_sport_rating(profile=profile, sport=match.sport)

        assert PlayerSportRating.objects.get(profile=profile, sport=match.sport).overall == earned

    def test_a_player_who_has_not_played_still_follows_their_self_assessment(self):
        from apps.accounts.tests.factories import UserFactory
        from apps.players.services import add_player_sport, get_or_create_profile
        from apps.sports.models import Sport

        profile = get_or_create_profile(UserFactory())
        sport = Sport.objects.get(slug="football")
        add_player_sport(profile=profile, sport=sport, skills={"finishing": 70, "passing": 70})
        high = PlayerSportRating.objects.get(profile=profile, sport=sport).overall

        set_player_skills(profile=profile, sport=sport, values={"finishing": 20, "passing": 20})
        refresh_sport_rating(profile=profile, sport=sport)

        assert PlayerSportRating.objects.get(profile=profile, sport=sport).overall < high


class TestRecomputeCommand:
    def test_the_command_reports_what_it_checked(self):
        match, profile = played()
        out = StringIO()

        call_command("recompute_ratings", f"--player={profile.id}", stdout=out)

        assert "Checked" in out.getvalue()

    def test_a_dry_run_writes_nothing(self):
        match, profile = played()
        rating = PlayerSportRating.objects.get(profile=profile, sport=match.sport)
        # Put the stored rating somewhere a replay would move it away from.
        PlayerSportRating.objects.filter(pk=rating.pk).update(overall=11)
        out = StringIO()

        call_command("recompute_ratings", f"--player={profile.id}", "--dry-run", stdout=out)

        rating.refresh_from_db()
        assert rating.overall == 11
        assert "would change" in out.getvalue()
