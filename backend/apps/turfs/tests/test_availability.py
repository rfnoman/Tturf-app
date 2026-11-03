"""Slot availability (DOMAIN §4) — the part Phase 03 will book against."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest
from django.utils import timezone

from apps.core.utils import DHAKA
from apps.turfs.availability import (
    TimeRange,
    clear_booked_range_providers,
    get_availability,
    opening_windows,
    price_for,
    register_booked_range_provider,
    uncovered_minutes,
)
from apps.turfs.models import OperatingHours

from .factories import (
    ApprovedTurfFactory,
    ClosureFactory,
    GroundFactory,
    OperatingHoursFactory,
    PriceRuleFactory,
    open_all_week,
    price_everything,
)

pytestmark = pytest.mark.django_db

#: A Wednesday, well in the future so "past slots are dropped" never interferes.
FUTURE = date(2027, 6, 2)
assert FUTURE.weekday() == 2


@pytest.fixture(autouse=True)
def no_booking_providers():
    """Phase 03 registers one at import time; tests opt in explicitly."""
    clear_booked_range_providers()
    yield
    clear_booked_range_providers()


@pytest.fixture
def turf():
    return ApprovedTurfFactory()


@pytest.fixture
def ground(turf):
    open_all_week(turf)
    ground = GroundFactory(turf=turf, slot_minutes=60)
    price_everything(ground)
    return ground


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=DHAKA)


class TestOpeningWindows:
    def test_a_normal_day(self, turf):
        OperatingHoursFactory(
            turf=turf, weekday=FUTURE.weekday(), open_time=time(8), close_time=time(22)
        )
        windows = opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE)

        assert len(windows) == 1
        assert windows[0].start == local(FUTURE, 8)
        assert windows[0].end == local(FUTURE, 22)

    def test_a_day_the_turf_is_shut(self, turf):
        OperatingHoursFactory(turf=turf, weekday=(FUTURE.weekday() + 3) % 7)
        assert opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE) == []

    def test_closing_after_midnight_extends_into_the_next_day(self, turf):
        """18:00–02:00 is a normal Dhaka evening, not an empty window."""
        OperatingHoursFactory(
            turf=turf, weekday=FUTURE.weekday(), open_time=time(18), close_time=time(2)
        )
        windows = opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE)

        assert len(windows) == 1
        assert windows[0].start == local(FUTURE, 18)
        assert windows[0].end == local(FUTURE + timedelta(days=1), 2)

    def test_yesterdays_tail_appears_on_todays_date(self, turf):
        """Tuesday 18:00–02:00 puts 00:00–02:00 on Wednesday, and it must be bookable."""
        OperatingHoursFactory(
            turf=turf,
            weekday=(FUTURE.weekday() - 1) % 7,
            open_time=time(18),
            close_time=time(2),
        )
        windows = opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE)

        assert len(windows) == 1
        assert windows[0].start == local(FUTURE, 0)
        assert windows[0].end == local(FUTURE, 2)

    def test_both_halves_appear_when_open_every_day(self, turf):
        open_all_week(turf, opens=time(18), closes=time(2))
        windows = opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE)

        assert len(windows) == 2
        assert windows[0].start == local(FUTURE, 0)
        assert windows[1].end == local(FUTURE + timedelta(days=1), 2)

    def test_a_midnight_close_is_a_full_evening_not_an_empty_window(self, turf):
        """close_time 00:00 is "until midnight", which must not slice to nothing."""
        OperatingHoursFactory(
            turf=turf, weekday=FUTURE.weekday(), open_time=time(6), close_time=time(0)
        )
        windows = opening_windows(turf_hours=list(turf.operating_hours.all()), day=FUTURE)

        assert windows[0].start == local(FUTURE, 6)
        assert windows[0].end == local(FUTURE + timedelta(days=1), 0)


class TestSlicing:
    def test_slices_the_window_by_slot_minutes(self, ground):
        slots = get_availability(ground=ground, day=FUTURE)
        assert len(slots) == 14  # 08:00–22:00 in one-hour slots
        assert slots[0].start == local(FUTURE, 8)
        assert slots[-1].end == local(FUTURE, 22)

    def test_slots_do_not_overlap_and_leave_no_gap(self, ground):
        slots = get_availability(ground=ground, day=FUTURE)
        for earlier, later in pairwise(slots):
            assert earlier.end == later.start

    def test_a_partial_slot_at_closing_time_is_not_offered(self, turf):
        """A 90-minute slot cannot start at 21:00 when the turf shuts at 22:00."""
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf, slot_minutes=90)
        price_everything(ground)

        slots = get_availability(ground=ground, day=FUTURE)
        assert slots[-1].end <= local(FUTURE, 22)
        assert len(slots) == 9  # 9 x 90 minutes = 13.5h of the 14h window

    def test_a_shut_day_has_no_slots(self, turf):
        OperatingHoursFactory(turf=turf, weekday=(FUTURE.weekday() + 2) % 7)
        ground = GroundFactory(turf=turf)
        price_everything(ground)
        assert get_availability(ground=ground, day=FUTURE) == []

    def test_past_slots_are_dropped_by_default(self, turf):
        """Today's morning slots are of no use at 3pm."""
        open_all_week(turf, opens=time(0), closes=time(0))
        ground = GroundFactory(turf=turf, slot_minutes=60)
        price_everything(ground)
        today = timezone.now().astimezone(DHAKA).date()

        starts = [slot.start for slot in get_availability(ground=ground, day=today)]
        assert all(start >= timezone.now() for start in starts)

    def test_include_past_keeps_them(self, turf):
        open_all_week(turf, opens=time(0), closes=time(0))
        ground = GroundFactory(turf=turf, slot_minutes=60)
        price_everything(ground)
        today = timezone.now().astimezone(DHAKA).date()

        assert len(get_availability(ground=ground, day=today, include_past=True)) == 24


class TestPricing:
    def test_the_most_specific_rule_wins(self, turf):
        """A broad all-week rule must not beat a narrow Friday-night override."""
        open_all_week(turf)
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground,
            weekdays=[],
            start_time=time(0),
            end_time=time(0),
            price="1500.00",
            label="Standard",
        )
        PriceRuleFactory(
            ground=ground,
            weekdays=[FUTURE.weekday()],
            start_time=time(18),
            end_time=time(22),
            price="3000.00",
            label="Peak",
        )

        rules = list(ground.price_rules.all())
        assert price_for(rules=rules, start=local(FUTURE, 10)) == (Decimal("1500.00"), "Standard")
        assert price_for(rules=rules, start=local(FUTURE, 19)) == (Decimal("3000.00"), "Peak")

    def test_a_slot_is_priced_by_the_band_it_starts_in(self, turf):
        """A 90-minute booking straddling the boundary must not be repriced halfway."""
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf, slot_minutes=90)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(17), price="1000.00"
        )
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(17), end_time=time(22), price="2000.00"
        )

        rules = list(ground.price_rules.all())
        price, _ = price_for(rules=rules, start=local(FUTURE, 16))
        assert price == Decimal("1000.00")

    def test_a_rule_crossing_midnight_covers_both_sides(self, turf):
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(22), end_time=time(2), price="1800.00"
        )
        rules = list(ground.price_rules.all())

        assert price_for(rules=rules, start=local(FUTURE, 23))[0] == Decimal("1800.00")
        assert price_for(rules=rules, start=local(FUTURE, 0, 30))[0] == Decimal("1800.00")
        assert price_for(rules=rules, start=local(FUTURE, 12))[0] is None

    def test_an_unpriced_slot_is_unavailable_rather_than_free(self, turf):
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(12), price="1000.00"
        )

        slots = {
            slot.start.astimezone(DHAKA).hour: slot
            for slot in get_availability(ground=ground, day=FUTURE)
        }
        assert slots[9].available is True
        assert slots[14].available is False
        assert slots[14].reason == "unpriced"


class TestUncoveredMinutes:
    def test_full_coverage_reports_no_gaps(self, ground):
        assert uncovered_minutes(ground=ground) == []

    def test_reports_the_gap(self, turf):
        OperatingHoursFactory(
            turf=turf, weekday=FUTURE.weekday(), open_time=time(8), close_time=time(22)
        )
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(20), price="1000.00"
        )

        gaps = uncovered_minutes(ground=ground)
        assert gaps == [(FUTURE.weekday(), time(20, 0), time(22, 0))]

    def test_reports_a_gap_in_the_middle(self, turf):
        OperatingHoursFactory(
            turf=turf, weekday=FUTURE.weekday(), open_time=time(8), close_time=time(22)
        )
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(12), price="1.00"
        )
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(14), end_time=time(22), price="1.00"
        )

        assert uncovered_minutes(ground=ground) == [(FUTURE.weekday(), time(12, 0), time(14, 0))]

    def test_a_weekday_specific_rule_does_not_cover_other_days(self, turf):
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[0], start_time=time(8), end_time=time(22), price="1.00"
        )

        gaps = uncovered_minutes(ground=ground)
        assert len(gaps) == 6
        assert {weekday for weekday, _, _ in gaps} == {1, 2, 3, 4, 5, 6}

    def test_coverage_follows_hours_past_midnight(self, turf):
        """The 00:00–02:00 tail needs a price too, on the following weekday."""
        OperatingHoursFactory(turf=turf, weekday=0, open_time=time(18), close_time=time(2))
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[0], start_time=time(18), end_time=time(0), price="1.00"
        )

        gaps = uncovered_minutes(ground=ground)
        assert gaps == [(1, time(0, 0), time(2, 0))]


class TestClosures:
    def test_a_turf_closure_blocks_the_slots_it_covers(self, ground):
        ClosureFactory(
            turf=ground.turf,
            ground=None,
            starts_at=local(FUTURE, 10),
            ends_at=local(FUTURE, 12),
        )
        slots = {
            s.start.astimezone(DHAKA).hour: s for s in get_availability(ground=ground, day=FUTURE)
        }

        assert slots[9].available is True
        assert slots[10].available is False
        assert slots[10].reason == "closed"
        assert slots[11].available is False
        assert slots[12].available is True

    def test_a_closure_on_another_ground_does_not_affect_this_one(self, ground):
        other = GroundFactory(turf=ground.turf)
        ClosureFactory(
            turf=ground.turf,
            ground=other,
            starts_at=local(FUTURE, 10),
            ends_at=local(FUTURE, 12),
        )
        slots = {
            s.start.astimezone(DHAKA).hour: s for s in get_availability(ground=ground, day=FUTURE)
        }
        assert slots[10].available is True

    def test_a_ground_closure_blocks_that_ground(self, ground):
        ClosureFactory(
            turf=ground.turf,
            ground=ground,
            starts_at=local(FUTURE, 10),
            ends_at=local(FUTURE, 12),
        )
        slots = {
            s.start.astimezone(DHAKA).hour: s for s in get_availability(ground=ground, day=FUTURE)
        }
        assert slots[10].available is False

    def test_a_closure_touching_a_slot_boundary_does_not_block_it(self, ground):
        """Half-open ranges: a closure ending at 10:00 leaves the 10:00 slot bookable."""
        ClosureFactory(
            turf=ground.turf, ground=None, starts_at=local(FUTURE, 8), ends_at=local(FUTURE, 10)
        )
        slots = {
            s.start.astimezone(DHAKA).hour: s for s in get_availability(ground=ground, day=FUTURE)
        }
        assert slots[9].available is False
        assert slots[10].available is True


class TestBookedRangeProvider:
    """The seam Phase 03 plugs into, so this selector never needs rewriting."""

    def test_no_provider_means_everything_is_free(self, ground):
        assert all(slot.available for slot in get_availability(ground=ground, day=FUTURE))

    def test_a_registered_provider_marks_slots_booked(self, ground):
        def provider(*, ground, start, end):
            return [TimeRange(local(FUTURE, 14), local(FUTURE, 15))]

        register_booked_range_provider(provider)

        slots = {
            s.start.astimezone(DHAKA).hour: s for s in get_availability(ground=ground, day=FUTURE)
        }
        assert slots[14].available is False
        assert slots[14].reason == "booked"
        assert slots[13].available is True

    def test_registering_the_same_provider_twice_is_a_no_op(self, ground):
        """AppConfig.ready() runs more than once under the autoreloader."""

        def provider(*, ground, start, end):
            return []

        register_booked_range_provider(provider)
        register_booked_range_provider(provider)

        from apps.turfs import availability

        assert availability._booked_range_providers.count(provider) == 1

    def test_a_provider_is_asked_only_about_the_days_span(self, ground):
        seen = {}

        def provider(*, ground, start, end):
            seen["start"], seen["end"] = start, end
            return []

        register_booked_range_provider(provider)
        get_availability(ground=ground, day=FUTURE)

        assert seen["start"] == local(FUTURE, 8)
        assert seen["end"] == local(FUTURE, 22)


def test_slot_minutes_matches_the_ground(turf):
    open_all_week(turf, opens=time(8), closes=time(20))
    ground = GroundFactory(turf=turf, slot_minutes=120)
    price_everything(ground)

    slots = get_availability(ground=ground, day=FUTURE)
    assert all(slot.minutes == 120 for slot in slots)
    assert len(slots) == 6


def test_two_opening_rows_on_one_day_produce_two_blocks(turf):
    """Some turfs shut for the afternoon; availability must respect the break."""
    OperatingHoursFactory(
        turf=turf, weekday=FUTURE.weekday(), open_time=time(6), close_time=time(10)
    )
    OperatingHoursFactory(
        turf=turf, weekday=FUTURE.weekday(), open_time=time(16), close_time=time(22)
    )
    ground = GroundFactory(turf=turf, slot_minutes=60)
    price_everything(ground)

    hours = sorted(
        s.start.astimezone(DHAKA).hour for s in get_availability(ground=ground, day=FUTURE)
    )
    assert hours == [6, 7, 8, 9, 16, 17, 18, 19, 20, 21]


def test_operating_hours_knows_when_it_crosses_midnight():
    assert OperatingHours(open_time=time(18), close_time=time(2)).crosses_midnight is True
    assert OperatingHours(open_time=time(8), close_time=time(22)).crosses_midnight is False
    assert OperatingHours(open_time=time(6), close_time=time(0)).crosses_midnight is True
