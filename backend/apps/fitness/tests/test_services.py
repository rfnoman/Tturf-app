"""Activity, weeks, streaks, goals and quiet hours (DOMAIN §10).

The week boundary tests are the point of this file: a Bangladeshi week runs Saturday to
Friday (DECISIONS D56), and every off-by-one here is a player told their streak is gone.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import override_settings

from apps.accounts.tests.factories import UserFactory
from apps.fitness.models import ActivityLog, ActivitySource, GoalType, ReminderPreference
from apps.fitness.services import (
    add_bundle_to_cart,
    estimate_calories,
    goal_progress,
    in_quiet_hours,
    log_manual_activity,
    log_match_activity,
    set_goal,
    should_send,
    streak_for,
    week_range,
    week_start,
    weekly_summary,
)
from apps.players.services import get_or_create_profile

pytestmark = pytest.mark.django_db


class TestWeeks:
    """Saturday to Friday, in Dhaka."""

    def test_a_saturday_starts_its_own_week(self):
        saturday = date(2026, 11, 7)
        assert saturday.weekday() == settings.FITNESS_WEEK_STARTS_ON
        assert week_start(saturday) == saturday

    def test_a_friday_belongs_to_the_week_that_began_six_days_earlier(self):
        friday = date(2026, 11, 13)
        assert week_start(friday) == date(2026, 11, 7)

    def test_friday_night_and_the_next_saturday_are_different_weeks(self):
        """The boundary the decision is about."""
        assert week_start(date(2026, 11, 13)) != week_start(date(2026, 11, 14))

    def test_a_week_is_seven_days_inclusive(self):
        start, end = week_range(date(2026, 11, 10))
        assert (start, end) == (date(2026, 11, 7), date(2026, 11, 13))

    def test_every_day_of_a_week_agrees_on_where_it_started(self):
        start = date(2026, 11, 7)
        for offset in range(7):
            assert week_start(start + timedelta(days=offset)) == start


class TestCalories:
    def test_met_times_weight_times_hours(self):
        """DOMAIN §10, worked by hand: 7 MET × 80 kg × 1.5 h = 840."""
        burn = estimate_calories(met=Decimal("7"), weight_kg=80, minutes=90)
        assert burn.calories == 840
        assert burn.is_estimate is False

    def test_a_missing_weight_uses_the_fallback_and_says_so(self):
        burn = estimate_calories(met=Decimal("7"), weight_kg=None, minutes=60)
        assert burn.calories == 7 * int(settings.FITNESS_FALLBACK_WEIGHT_KG)
        assert burn.is_estimate is True

    def test_half_an_hour_is_half_the_calories(self):
        full = estimate_calories(met=Decimal("8"), weight_kg=70, minutes=60).calories
        half = estimate_calories(met=Decimal("8"), weight_kg=70, minutes=30).calories
        assert half * 2 == full

    def test_a_gentler_sport_burns_less(self):
        football = estimate_calories(met=Decimal("8"), weight_kg=70, minutes=60).calories
        badminton = estimate_calories(met=Decimal("5.5"), weight_kg=70, minutes=60).calories
        assert badminton < football


def onboard(user, *, weight=None):
    profile = get_or_create_profile(user)
    if weight is not None:
        profile.weight_kg = Decimal(str(weight))
        profile.save(update_fields=["weight_kg"])
    return profile


class TestMatchActivity:
    def test_a_locked_match_logs_everybody_who_played(self):
        from apps.ratings.tests.factories import locked_match

        match, _teams, _scorecard = locked_match(players=4)

        logs = ActivityLog.objects.filter(match=match)
        assert logs.count() == 4
        assert all(log.source == ActivitySource.MATCH for log in logs)

    def test_the_log_uses_the_bookings_own_length(self):
        from apps.ratings.tests.factories import locked_match

        match, _teams, _scorecard = locked_match(players=2)
        booking = match.booking
        expected = int((booking.time_range.upper - booking.time_range.lower).total_seconds() // 60)

        assert ActivityLog.objects.filter(match=match).first().minutes == expected

    def test_logging_the_same_match_twice_changes_nothing(self):
        from apps.ratings.tests.factories import locked_match

        match, _teams, scorecard = locked_match(players=2)
        before = ActivityLog.objects.filter(match=match).count()

        log_match_activity(scorecard=scorecard)

        assert ActivityLog.objects.filter(match=match).count() == before

    def test_a_player_who_did_not_turn_up_gets_nothing(self):
        from apps.ratings.tests.factories import locked_match

        match, _teams, _scorecard = locked_match(players=2)
        ActivityLog.objects.filter(match=match).delete()
        absent = match.players.first()
        absent.attended = False
        absent.save(update_fields=["attended"])

        log_match_activity(match=match)

        assert not ActivityLog.objects.filter(match=match, player=absent.player).exists()

    def test_a_match_with_no_scorecard_can_still_be_logged(self):
        """A game nobody scored still happened."""
        from apps.scoring.tests.factories import played_match

        match = played_match(players=2)

        logs = log_match_activity(match=match)

        assert len(logs) == 2


class TestManualActivity:
    def test_a_gym_session_counts(self):
        user = UserFactory()
        onboard(user, weight=70)

        log = log_manual_activity(player=user, minutes=45, note="Gym")

        assert log.source == ActivitySource.MANUAL
        assert log.sport is None
        assert log.est_calories > 0

    def test_a_session_in_the_future_is_refused(self):
        with pytest.raises(Exception, match="future"):
            log_manual_activity(
                player=UserFactory(), minutes=30, happened_on=date.today() + timedelta(days=2)
            )

    def test_an_impossible_length_is_refused(self):
        with pytest.raises(Exception, match="more than a day"):
            log_manual_activity(player=UserFactory(), minutes=2000)

    def test_zero_minutes_is_refused(self):
        with pytest.raises(Exception, match="How long"):
            log_manual_activity(player=UserFactory(), minutes=0)


def log_on(user, day: date, *, minutes=60, source=ActivitySource.MATCH, calories=400):
    return ActivityLog.objects.create(
        player=user,
        happened_on=day,
        minutes=minutes,
        source=source,
        est_calories=calories,
    )


class TestWeeklySummary:
    def test_it_adds_up_the_week(self):
        user = UserFactory()
        log_on(user, date(2026, 11, 7), minutes=60, calories=400)
        log_on(user, date(2026, 11, 10), minutes=90, calories=600)
        # Last week: must not count.
        log_on(user, date(2026, 11, 6), minutes=30, calories=200)

        summary = weekly_summary(player=user, day=date(2026, 11, 10))

        assert summary["minutes"] == 150
        assert summary["calories"] == 1000
        assert summary["sessions"] == 2

    def test_a_friday_night_match_counts_in_the_week_that_is_ending(self):
        user = UserFactory()
        log_on(user, date(2026, 11, 13))

        assert weekly_summary(player=user, day=date(2026, 11, 13))["minutes"] == 60
        # …and not in the one starting the next day.
        assert weekly_summary(player=user, day=date(2026, 11, 14))["minutes"] == 0

    def test_an_empty_week_is_zeroes_not_an_error(self):
        summary = weekly_summary(player=UserFactory())
        assert summary["minutes"] == 0
        assert summary["by_sport"] == []


class TestStreaks:
    def test_three_weeks_in_a_row(self):
        user = UserFactory()
        for weeks_ago in range(3):
            log_on(user, date(2026, 11, 7) - timedelta(days=7 * weeks_ago))

        streak = streak_for(player=user, day=date(2026, 11, 10))

        assert streak["current"] == 3
        assert streak["best"] == 3
        assert streak["played_this_week"] is True

    def test_a_missed_week_breaks_it(self):
        user = UserFactory()
        log_on(user, date(2026, 11, 7))
        log_on(user, date(2026, 10, 24))  # two weeks earlier

        assert streak_for(player=user, day=date(2026, 11, 10))["current"] == 1

    def test_a_streak_survives_until_this_week_is_over(self):
        """Played last week, not yet this week: still alive, and worth saving."""
        user = UserFactory()
        log_on(user, date(2026, 10, 31))

        streak = streak_for(player=user, day=date(2026, 11, 10))

        assert streak["current"] == 1
        assert streak["played_this_week"] is False

    def test_the_best_run_is_remembered_after_it_breaks(self):
        user = UserFactory()
        for weeks_ago in (6, 7, 8, 9):
            log_on(user, date(2026, 11, 7) - timedelta(days=7 * weeks_ago))
        log_on(user, date(2026, 11, 7))

        streak = streak_for(player=user, day=date(2026, 11, 10))

        assert streak["current"] == 1
        assert streak["best"] == 4

    def test_a_manual_session_does_not_keep_a_streak_alive(self):
        """The streak is about turning up to play."""
        user = UserFactory()
        log_on(user, date(2026, 11, 7), source=ActivitySource.MANUAL)

        assert streak_for(player=user, day=date(2026, 11, 10))["current"] == 0

    def test_somebody_who_has_never_played_has_no_streak(self):
        assert streak_for(player=UserFactory()) == {
            "current": 0,
            "best": 0,
            "played_this_week": False,
        }


class TestGoals:
    def test_progress_against_a_minutes_goal(self):
        user = UserFactory()
        set_goal(player=user, type=GoalType.MINUTES, target=180)
        log_on(user, date(2026, 11, 9), minutes=90)

        progress = goal_progress(player=user, day=date(2026, 11, 10))[0]

        assert progress["achieved"] == 90
        assert progress["percent"] == 50

    def test_progress_is_capped_at_a_hundred(self):
        user = UserFactory()
        set_goal(player=user, type=GoalType.MATCHES, target=1)
        log_on(user, date(2026, 11, 9))
        log_on(user, date(2026, 11, 10))

        assert goal_progress(player=user, day=date(2026, 11, 10))[0]["percent"] == 100

    def test_setting_a_goal_twice_replaces_it(self):
        user = UserFactory()
        set_goal(player=user, type=GoalType.MINUTES, target=120)
        set_goal(player=user, type=GoalType.MINUTES, target=240)

        goals = goal_progress(player=user)
        assert len(goals) == 1
        assert goals[0]["target"] == 240

    def test_a_goal_of_zero_retires_it(self):
        """Zero is how the UI says "drop this one"."""
        user = UserFactory()
        set_goal(player=user, type=GoalType.MINUTES, target=120)

        assert set_goal(player=user, type=GoalType.MINUTES, target=0) is None
        assert goal_progress(player=user) == []

    def test_an_unknown_goal_type_is_refused(self):
        with pytest.raises(Exception, match="Unknown goal"):
            set_goal(player=UserFactory(), type="vibes_per_week", target=3)


class TestQuietHours:
    def make(self, **kwargs) -> ReminderPreference:
        return ReminderPreference.objects.create(player=UserFactory(), **kwargs)

    def test_the_default_window_wraps_midnight(self):
        preference = self.make()
        from datetime import datetime

        from apps.core.utils import DHAKA

        middle_of_the_night = datetime(2026, 11, 10, 2, 0, tzinfo=DHAKA)
        lunchtime = datetime(2026, 11, 10, 13, 0, tzinfo=DHAKA)

        assert in_quiet_hours(preference, moment=middle_of_the_night) is True
        assert in_quiet_hours(preference, moment=lunchtime) is False

    def test_a_player_can_set_their_own(self):
        from datetime import datetime

        from apps.core.utils import DHAKA

        preference = self.make(quiet_from=time(13, 0), quiet_until=time(15, 0))

        assert in_quiet_hours(preference, moment=datetime(2026, 11, 10, 14, 0, tzinfo=DHAKA))
        assert not in_quiet_hours(preference, moment=datetime(2026, 11, 10, 16, 0, tzinfo=DHAKA))

    def test_an_empty_window_silences_nothing(self):
        preference = self.make(quiet_from=time(9, 0), quiet_until=time(9, 0))
        assert in_quiet_hours(preference) is False

    def test_a_switched_off_reminder_is_not_sent(self):
        from datetime import datetime

        from apps.core.utils import DHAKA

        user = UserFactory()
        ReminderPreference.objects.create(player=user, hydration=False)
        noon = datetime(2026, 11, 10, 12, 0, tzinfo=DHAKA)

        assert should_send(player=user, kind="hydration", moment=noon) is False
        assert should_send(player=user, kind="recovery", moment=noon) is True

    def test_nothing_is_sent_during_quiet_hours(self):
        from datetime import datetime

        from apps.core.utils import DHAKA

        user = UserFactory()
        ReminderPreference.objects.create(player=user)

        assert (
            should_send(
                player=user, kind="hydration", moment=datetime(2026, 11, 10, 3, 0, tzinfo=DHAKA)
            )
            is False
        )

    def test_preferences_appear_on_first_read(self):
        from apps.fitness.services import reminder_preference

        user = UserFactory()
        assert reminder_preference(user).hydration is True


class TestBundles:
    def make_bundle(self, *, turf=None, products=()):
        from apps.fitness.models import Bundle, BundleItem

        bundle = Bundle.objects.create(
            name="Evening football kit", slug=f"kit-{turf.id if turf else 'platform'}", turf=turf
        )
        for product, quantity in products:
            BundleItem.objects.create(bundle=bundle, product=product, quantity=quantity)
        return bundle

    def test_one_tap_adds_the_whole_kit(self):
        from apps.store.services import cart_by_source
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", price="20.00", on_hand=10)
        bar, _bar_item = platform_product(name="Protein bar", price="220.00", on_hand=10)
        bundle = self.make_bundle(products=[(water, 2), (bar, 1)])
        player = UserFactory()

        result = add_bundle_to_cart(player=player, bundle=bundle)

        assert len(result["added"]) == 2
        assert result["missing"] == []
        lines = next(iter(cart_by_source(user=player).values()))
        assert sum(line.quantity for line in lines) == 3

    def test_partial_stock_adds_what_there_is_and_says_what_is_missing(self):
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", on_hand=1)
        bar, _bar_item = platform_product(name="Protein bar", on_hand=0)
        bundle = self.make_bundle(products=[(water, 3), (bar, 1)])

        result = add_bundle_to_cart(player=UserFactory(), bundle=bundle)

        assert result["added"] == [{"product": "Water", "quantity": 1}]
        assert "Protein bar" in result["missing"]
        assert any("only 1" in entry for entry in result["missing"])

    def test_a_bundle_with_nothing_in_stock_is_refused(self):
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", on_hand=0)
        bundle = self.make_bundle(products=[(water, 1)])

        with pytest.raises(Exception, match="in stock"):
            add_bundle_to_cart(player=UserFactory(), bundle=bundle)

    def test_a_turf_bundle_comes_off_that_turfs_shelf(self):
        from apps.store.tests.factories import turf_shelf

        turf, _cashier, product, item = turf_shelf(name="Banana", on_hand=5)
        bundle = self.make_bundle(turf=turf, products=[(product, 2)])
        player = UserFactory()

        result = add_bundle_to_cart(player=player, bundle=bundle)

        assert result["source_id"] == item.location_id

    def test_a_platform_bundle_always_comes_from_the_warehouse(self):
        """Its products are the platform's; no turf stocks those rows."""
        from apps.inventory.services import warehouse
        from apps.store.tests.factories import platform_product

        water, _item = platform_product(name="Water", on_hand=4)
        bundle = self.make_bundle(products=[(water, 1)])

        result = add_bundle_to_cart(player=UserFactory(), bundle=bundle)

        assert result["source_id"] == warehouse().id


@override_settings(FITNESS_FALLBACK_WEIGHT_KG=65)
def test_the_fallback_weight_is_configurable():
    assert estimate_calories(met=Decimal("1"), weight_kg=None, minutes=60).calories == 65
