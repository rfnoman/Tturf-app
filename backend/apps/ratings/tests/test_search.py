"""Player discovery and availability (DOMAIN §3)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.core.utils import now
from apps.players.services import add_player_sport, get_or_create_profile
from apps.ratings.models import Availability
from apps.ratings.selectors import availability_for, search_players, track_record
from apps.scoring.models import TeamSide
from apps.sports.models import Sport

from .factories import locked_match

pytestmark = pytest.mark.django_db


def player(*, name: str, area: str = "", sport: str = "football", discoverable: bool = True):
    profile = get_or_create_profile(UserFactory())
    profile.display_name = name
    profile.area = area
    profile.discoverable = discoverable
    profile.save()
    add_player_sport(profile=profile, sport=Sport.objects.get(slug=sport))
    return profile


class TestSearch:
    def test_finds_players_by_sport(self):
        footballer = player(name="Rafi", sport="football")
        player(name="Shuvo", sport="cricket")

        results = list(search_players(sport="football"))
        assert footballer in results
        assert all(r.player_sports.filter(sport__slug="football").exists() for r in results)

    def test_an_undiscoverable_player_is_not_in_the_results(self):
        """`discoverable` gates search only — a direct link still resolves (DOMAIN §3)."""
        hidden = player(name="Quiet", discoverable=False)
        assert hidden not in list(search_players())

    def test_the_viewer_is_not_in_their_own_results(self):
        mine = player(name="Me")
        assert mine not in list(search_players(viewer=mine.user))

    def test_filters_by_area(self):
        mirpur = player(name="Mirpur player", area="Mirpur")
        player(name="Uttara player", area="Uttara")

        results = list(search_players(area="Mirpur"))
        assert results == [mirpur]

    def test_filters_by_reliability(self):
        reliable = player(name="Reliable")
        flaky = player(name="Flaky")
        flaky.reliability_score = 40
        flaky.save(update_fields=["reliability_score"])

        results = list(search_players(reliability_min=80))
        assert reliable in results
        assert flaky not in results

    def test_filters_by_rating_band(self):
        strong = player(name="Strong")
        rating = strong.sport_ratings.get(sport__slug="football")
        rating.overall = 80
        rating.save(update_fields=["overall"])

        assert strong in list(search_players(sport="football", rating_min=75))
        assert strong not in list(search_players(sport="football", rating_max=60))

    def test_a_shared_area_ranks_above_a_stranger(self):
        """A good suggestion is somebody who will actually turn up nearby."""
        local = player(name="Local", area="Mirpur")
        far = player(name="Far", area="Uttara")
        far.reliability_score = 100
        far.save(update_fields=["reliability_score"])

        results = list(search_players(area="Mirpur"))
        assert results[0] == local
        assert far not in results

    def test_finds_players_who_said_they_are_free(self):
        free = player(name="Free tonight")
        busy = player(name="Busy")
        Availability.objects.create(
            profile=free,
            starts_at=now() + timedelta(hours=2),
            ends_at=now() + timedelta(hours=5),
            area="Mirpur",
        )

        results = list(
            search_players(
                available_from=now() + timedelta(hours=3),
                available_until=now() + timedelta(hours=4),
            )
        )
        assert free in results
        assert busy not in results

    def test_a_window_that_has_passed_does_not_match(self):
        past = player(name="Was free")
        Availability.objects.create(
            profile=past,
            starts_at=now() - timedelta(days=2),
            ends_at=now() - timedelta(days=1),
        )
        results = list(
            search_players(available_from=now(), available_until=now() + timedelta(hours=2))
        )
        assert past not in results

    def test_filters_by_where_somebody_has_played(self):
        match, teams, _ = locked_match()
        profile = teams[TeamSide.A].players.first().match_player.player.player_profile
        turf = match.booking.ground.turf

        assert profile in list(search_players(played_at_turf=turf.slug))
        assert profile not in list(search_players(played_at_turf="somewhere-else"))

    def test_each_player_appears_once(self):
        """Joining through player_sports and availability can multiply rows."""
        somebody = player(name="Doubled")
        for offset in (2, 4):
            Availability.objects.create(
                profile=somebody,
                starts_at=now() + timedelta(hours=offset),
                ends_at=now() + timedelta(hours=offset + 1),
            )
        results = list(
            search_players(available_from=now(), available_until=now() + timedelta(days=1))
        )
        assert results.count(somebody) == 1


class TestAvailability:
    def test_only_upcoming_windows_are_offered(self):
        profile = player(name="Mixed")
        Availability.objects.create(
            profile=profile,
            starts_at=now() - timedelta(days=3),
            ends_at=now() - timedelta(days=2),
        )
        upcoming = Availability.objects.create(
            profile=profile,
            starts_at=now() + timedelta(days=1),
            ends_at=now() + timedelta(days=1, hours=2),
        )
        assert list(availability_for(profile=profile)) == [upcoming]


class TestTrackRecord:
    def test_lists_where_somebody_has_played(self):
        match, teams, _ = locked_match(stats={TeamSide.A: {"goals": 2}}, scores=(2, 0))
        profile = teams[TeamSide.A].players.first().match_player.player.player_profile

        rows = track_record(profile=profile)
        assert len(rows) == 1
        assert rows[0]["turf_name"] == match.booking.ground.turf.name
        assert rows[0]["matches"] == 1
        assert rows[0]["stat_totals"]["goals"] == "2"
