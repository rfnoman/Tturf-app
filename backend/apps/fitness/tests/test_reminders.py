"""Reminder scheduling: who gets told, and when nobody is told (DOMAIN §10)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.test import override_settings

from apps.accounts.tests.factories import UserFactory
from apps.core.utils import DHAKA, now
from apps.fitness.models import ActivityLog, ReminderPreference
from apps.fitness.tasks import (
    hydration_reminder,
    match_day_summary,
    recovery_tip,
    weekly_recap,
)
from apps.matches.models import MatchPlayer
from apps.matches.services import add_player
from apps.matches.tests.factories import make_match
from apps.notifications.models import Notification, NotificationKind

pytestmark = pytest.mark.django_db


def match_in(hours: float, *, players=1):
    """A match that kicks off in `hours`, with its roster."""
    from psycopg.types.range import TimestamptzRange

    from apps.bookings.models import Booking

    match = make_match(booker=UserFactory(), hours_ahead=max(1, int(hours) or 1))
    for _ in range(players - 1):
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.INVITE)

    start = now() + timedelta(hours=hours)
    Booking.objects.filter(pk=match.booking_id).update(
        time_range=TimestamptzRange(start, start + timedelta(hours=1))
    )
    match.refresh_from_db()
    return match


def daytime():
    """A moment that is nobody's quiet hours, so the clock cannot flake the test."""
    return datetime.combine(now().astimezone(DHAKA).date(), time(13, 0), tzinfo=DHAKA)


class TestHydration:
    def test_it_goes_out_two_hours_before(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match_in(1.5, players=2)

        assert hydration_reminder() == 2
        assert Notification.objects.filter(kind=NotificationKind.HYDRATION).count() == 2

    def test_it_does_not_go_out_a_day_early(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match_in(20, players=2)

        assert hydration_reminder() == 0

    def test_it_is_sent_once_however_often_the_job_runs(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match_in(1.5, players=2)

        hydration_reminder()
        assert hydration_reminder() == 0

    def test_a_player_who_switched_it_off_is_left_alone(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match = match_in(1.5, players=2)
        for entry in match.players.all():
            ReminderPreference.objects.create(player=entry.player, hydration=False)

        assert hydration_reminder() == 0

    def test_nothing_is_sent_in_the_middle_of_the_night(self, monkeypatch):
        """The acceptance line: not during quiet hours."""
        night = datetime.combine(now().astimezone(DHAKA).date(), time(3, 0), tzinfo=DHAKA)
        monkeypatch.setattr("apps.fitness.services.now", lambda: night)
        match_in(1.5, players=2)

        assert hydration_reminder() == 0

    @override_settings(FITNESS_HYDRATION_LEAD_HOURS=6)
    def test_the_lead_time_is_configurable(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match_in(5, players=1)

        assert hydration_reminder() == 1


class TestMatchDay:
    def test_it_goes_out_on_the_day(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        # Far enough out not to be "today" only if the clock is near midnight; the
        # assertion below reads the match's own Dhaka date, so this is exact.
        match = match_in(3, players=2)
        from apps.core.utils import to_dhaka

        if to_dhaka(match.starts_at).date() != to_dhaka(now()).date():
            pytest.skip("match rolled past midnight Dhaka time")

        assert match_day_summary() == 2

    def test_tomorrows_match_waits(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match_in(36, players=2)

        assert match_day_summary() == 0


class TestRecovery:
    def finished_match(self, *, players=2):
        from psycopg.types.range import TimestamptzRange

        from apps.bookings.models import Booking

        match = match_in(2, players=players)
        ended = now() - timedelta(hours=1)
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(ended - timedelta(hours=1), ended)
        )
        match.refresh_from_db()
        return match

    def test_a_tip_goes_out_after_the_whistle(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        self.finished_match(players=2)

        assert recovery_tip() == 2
        assert Notification.objects.filter(kind=NotificationKind.RECOVERY).exists()

    def test_it_logs_the_activity_for_a_match_nobody_scored(self, monkeypatch):
        """The safety net: a game with no scorecard still counts as exercise."""
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match = self.finished_match(players=2)

        recovery_tip()

        assert ActivityLog.objects.filter(match=match).count() == 2

    def test_it_does_not_log_the_same_match_twice(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        match = self.finished_match(players=2)

        recovery_tip()
        recovery_tip()

        assert ActivityLog.objects.filter(match=match).count() == 2


class TestWeeklyRecap:
    def test_it_sums_up_last_week(self, monkeypatch):
        from apps.fitness.services import week_start

        monkeypatch.setattr("apps.fitness.services.now", daytime)
        player = UserFactory()
        last_week = week_start(now().astimezone(DHAKA).date()) - timedelta(days=7)
        ActivityLog.objects.create(
            player=player, happened_on=last_week, minutes=90, est_calories=600
        )

        assert weekly_recap() == 1
        notification = Notification.objects.get(kind=NotificationKind.WEEKLY_RECAP)
        assert "90" in notification.title

    def test_a_quiet_week_says_nothing(self, monkeypatch):
        monkeypatch.setattr("apps.fitness.services.now", daytime)
        UserFactory()

        assert weekly_recap() == 0

    def test_it_is_sent_once(self, monkeypatch):
        from apps.fitness.services import week_start

        monkeypatch.setattr("apps.fitness.services.now", daytime)
        player = UserFactory()
        last_week = week_start(now().astimezone(DHAKA).date()) - timedelta(days=7)
        ActivityLog.objects.create(player=player, happened_on=last_week, minutes=60)

        weekly_recap()
        assert weekly_recap() == 0
