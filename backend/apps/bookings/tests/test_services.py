"""The booking state machine, D3 auto-confirmation, and reliability (DOMAIN §5)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import override_settings
from psycopg.types.range import TimestamptzRange

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import Booking, BookingEvent, BookingStatus
from apps.bookings.services import (
    SlotTakenError,
    adjust_reliability,
    cancel_booking,
    complete_booking,
    complete_finished_bookings,
    confirm_booking,
    confirmation_deadline,
    create_booking,
    expire_booking,
    expire_overdue_bookings,
    is_late_cancellation,
    mark_no_show,
    mark_paid,
    should_auto_confirm,
)
from apps.core.utils import now
from apps.notifications.models import Notification, NotificationKind
from apps.payments.models import PaymentStatus
from apps.players.services import get_or_create_profile
from apps.turfs.models import Turf, TurfMembership
from apps.turfs.tests.factories import TurfMembershipFactory

from .factories import bookable_ground, next_slot_start

pytestmark = pytest.mark.django_db


@pytest.fixture
def ground_and_format():
    return bookable_ground()


@pytest.fixture
def ground(ground_and_format):
    return ground_and_format[0]


@pytest.fixture
def sport_format(ground_and_format):
    return ground_and_format[1]


@pytest.fixture
def player():
    return UserFactory()


@pytest.fixture
def staff(ground):
    member = TurfMembershipFactory(turf=ground.turf, role=TurfMembership.Role.CASHIER)
    return member.user


def book(user, ground, sport_format, **kwargs) -> Booking:
    return create_booking(
        user=user,
        ground=ground,
        start=kwargs.pop("start", next_slot_start()),
        sport_format=sport_format,
        **kwargs,
    )


def make_reliable(user) -> None:
    """Give a player the record D3 asks for: 3 completed bookings and high reliability."""
    profile = get_or_create_profile(user)
    profile.reliability_score = 100
    profile.save(update_fields=["reliability_score"])

    ground, sport_format = bookable_ground()
    past = now() - timedelta(days=7)
    for index in range(3):
        Booking.objects.create(
            ground=ground,
            booked_by=user,
            sport=sport_format.sport,
            sport_format=sport_format,
            time_range=TimestamptzRange(
                past + timedelta(hours=index * 2), past + timedelta(hours=index * 2 + 1)
            ),
            price="2000.00",
            status=BookingStatus.COMPLETED,
        )


class TestCreateBooking:
    def test_a_new_player_gets_a_reservation_awaiting_confirmation(
        self, player, ground, sport_format
    ):
        """DECISIONS D3: no track record means staff decide."""
        booking = book(player, ground, sport_format)

        assert booking.status == BookingStatus.RESERVED
        assert booking.auto_confirmed is False
        assert booking.expires_at is not None

    def test_a_reliable_player_is_confirmed_immediately(self, player, ground, sport_format):
        make_reliable(player)
        booking = book(player, ground, sport_format)

        assert booking.status == BookingStatus.CONFIRMED
        assert booking.auto_confirmed is True
        assert booking.expires_at is None

    def test_a_turf_can_insist_on_confirming_every_booking(self, player, ground, sport_format):
        make_reliable(player)
        ground.turf.auto_confirm_enabled = False
        ground.turf.save(update_fields=["auto_confirm_enabled"])

        assert book(player, ground, sport_format).status == BookingStatus.RESERVED

    def test_low_reliability_blocks_auto_confirmation(self, player, ground, sport_format):
        make_reliable(player)
        profile = get_or_create_profile(player)
        profile.reliability_score = settings.BOOKING_AUTO_CONFIRM_MIN_RELIABILITY - 1
        profile.save(update_fields=["reliability_score"])

        assert book(player, ground, sport_format).status == BookingStatus.RESERVED

    def test_the_price_comes_from_the_ground_not_the_client(self, player, ground, sport_format):
        booking = book(player, ground, sport_format)
        assert booking.price == Decimal("2000.00")

    def test_the_slot_must_be_one_the_turf_offers(self, player, ground, sport_format):
        """A start halfway through a slot is not an offered slot."""
        with pytest.raises(ValidationError) as exc:
            book(player, ground, sport_format, start=next_slot_start() + timedelta(minutes=17))
        assert "start" in exc.value.message_dict

    def test_the_past_cannot_be_booked(self, player, ground, sport_format):
        with pytest.raises(ValidationError) as exc:
            book(player, ground, sport_format, start=next_slot_start(hours_ahead=-48))
        assert "already started" in exc.value.message_dict["start"][0]

    def test_bookings_do_not_open_beyond_the_horizon(self, player, ground, sport_format):
        beyond = next_slot_start(hours_ahead=24 * (settings.BOOKING_HORIZON_DAYS + 2))
        with pytest.raises(ValidationError) as exc:
            book(player, ground, sport_format, start=beyond)
        assert "start" in exc.value.message_dict

    def test_an_unapproved_turf_takes_no_bookings(self, player, ground, sport_format):
        ground.turf.status = Turf.Status.SUSPENDED
        ground.turf.save(update_fields=["status"])

        with pytest.raises(ValidationError) as exc:
            book(player, ground, sport_format)
        assert "ground" in exc.value.message_dict

    def test_an_inactive_ground_takes_no_bookings(self, player, ground, sport_format):
        ground.is_active = False
        ground.save(update_fields=["is_active"])

        with pytest.raises(ValidationError):
            book(player, ground, sport_format)

    def test_a_format_the_ground_does_not_host_is_refused(self, player, ground):
        from apps.sports.models import SportFormat

        badminton = SportFormat.objects.get(sport__slug="badminton", slug="singles")
        with pytest.raises(ValidationError) as exc:
            book(player, ground, badminton)
        assert "sport_format" in exc.value.message_dict

    def test_a_player_cannot_be_in_two_places_at_once(self, player, ground, sport_format):
        """Even on a different ground: one person, one slot."""
        other, other_format = bookable_ground()
        start = next_slot_start()
        book(player, ground, sport_format, start=start)

        with pytest.raises(ValidationError) as exc:
            book(player, other, other_format, start=start)
        assert "already have a booking" in exc.value.message_dict["start"][0]

    def test_a_taken_slot_raises_slot_taken(self, player, ground, sport_format):
        start = next_slot_start()
        book(player, ground, sport_format, start=start)

        with pytest.raises(SlotTakenError):
            book(UserFactory(), ground, sport_format, start=start)

    def test_creation_records_an_event(self, player, ground, sport_format):
        booking = book(player, ground, sport_format)
        event = booking.events.get()
        assert event.from_status == ""
        assert event.to_status == BookingStatus.RESERVED

    def test_creation_notifies_the_player_and_the_staff(self, player, ground, sport_format, staff):
        book(player, ground, sport_format)

        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_CREATED
        ).exists()
        assert Notification.objects.filter(
            user=staff, kind=NotificationKind.BOOKING_PENDING_CONFIRMATION
        ).exists()

    def test_an_auto_confirmed_booking_tells_the_player_it_is_confirmed(
        self, player, ground, sport_format, staff
    ):
        make_reliable(player)
        book(player, ground, sport_format)

        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_CONFIRMED
        ).exists()
        # Nothing for staff to do, so they are not pinged.
        assert not Notification.objects.filter(
            user=staff, kind=NotificationKind.BOOKING_PENDING_CONFIRMATION
        ).exists()


class TestConfirmationDeadline:
    def test_two_hours_out_for_a_distant_slot(self):
        start = now() + timedelta(days=5)
        deadline = confirmation_deadline(start=start)
        assert deadline - now() <= timedelta(hours=settings.BOOKING_CONFIRM_WINDOW_HOURS)

    def test_an_imminent_slot_is_cut_off_an_hour_before_kickoff(self):
        """A slot released after the game would have started helps nobody."""
        start = now() + timedelta(minutes=90)
        deadline = confirmation_deadline(start=start)
        assert deadline == start - timedelta(
            hours=settings.BOOKING_CONFIRM_CUTOFF_HOURS_BEFORE_START
        )


class TestTransitions:
    def test_confirm(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)

        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.confirmed_by == staff
        assert booking.expires_at is None
        assert booking.events.filter(to_status=BookingStatus.CONFIRMED).exists()
        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_CONFIRMED
        ).exists()

    def test_a_confirmed_booking_cannot_be_confirmed_again(
        self, player, ground, sport_format, staff
    ):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        with pytest.raises(ValidationError):
            confirm_booking(booking=booking, actor=staff)

    def test_expire(self, player, ground, sport_format):
        booking = book(player, ground, sport_format)
        expire_booking(booking=booking)

        booking.refresh_from_db()
        assert booking.status == BookingStatus.EXPIRED
        assert booking.expires_at is None
        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_EXPIRED
        ).exists()

    def test_a_confirmed_booking_cannot_expire(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        with pytest.raises(ValidationError):
            expire_booking(booking=booking)

    def test_mark_paid_requires_confirmation_first(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        with pytest.raises(ValidationError):
            mark_paid(booking=booking, actor=staff)

    def test_mark_paid_records_the_cash(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff)

        booking.refresh_from_db()
        assert booking.status == BookingStatus.PAID
        payment = booking.payments.get()
        assert payment.status == PaymentStatus.PAID
        assert payment.amount == booking.price
        assert payment.collected_by == staff

    def test_mark_paid_accepts_a_discounted_amount(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff, amount=Decimal("1500.00"))

        assert booking.payments.get().amount == Decimal("1500.00")

    def test_complete_requires_the_slot_to_have_finished(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff)

        with pytest.raises(ValidationError) as exc:
            complete_booking(booking=booking)
        assert "not finished" in exc.value.message_dict["status"][0]

    def test_complete_restores_reliability(self, player, ground, sport_format, staff):
        profile = get_or_create_profile(player)
        adjust_reliability(profile=profile, delta=-20)
        before = profile.reliability_score

        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff)
        # Pretend the slot has been and gone.
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(now() - timedelta(hours=2), now() - timedelta(hours=1))
        )
        booking.refresh_from_db()
        complete_booking(booking=booking)

        profile.refresh_from_db()
        assert profile.reliability_score == before + settings.RELIABILITY_COMPLETED_MATCH_DELTA

    def test_no_show_waits_for_the_grace_period(self, player, ground, sport_format, staff):
        """A player stuck in Dhaka traffic three minutes away is not a no-show."""
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)

        with pytest.raises(ValidationError) as exc:
            mark_no_show(booking=booking, actor=staff)
        assert "minutes after" in exc.value.message_dict["status"][0]

    def test_no_show_costs_reliability(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        started = now() - timedelta(hours=2)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(started, started + timedelta(hours=1))
        )
        booking.refresh_from_db()
        profile = get_or_create_profile(player)
        before = profile.reliability_score

        mark_no_show(booking=booking, actor=staff)

        booking.refresh_from_db()
        profile.refresh_from_db()
        assert booking.status == BookingStatus.NO_SHOW
        assert profile.reliability_score == before + settings.RELIABILITY_NO_SHOW_DELTA
        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_NO_SHOW
        ).exists()

    def test_a_cancelled_booking_cannot_be_confirmed(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        cancel_booking(booking=booking, actor=player)
        with pytest.raises(ValidationError):
            confirm_booking(booking=booking, actor=staff)

    @pytest.mark.parametrize(
        "terminal",
        [
            BookingStatus.COMPLETED,
            BookingStatus.EXPIRED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        ],
    )
    def test_terminal_states_accept_nothing(self, player, ground, sport_format, staff, terminal):
        booking = book(player, ground, sport_format)
        Booking.objects.filter(pk=booking.pk).update(status=terminal)
        booking.refresh_from_db()

        for service in (confirm_booking, expire_booking):
            with pytest.raises(ValidationError):
                service(booking=booking)
        with pytest.raises(ValidationError):
            mark_paid(booking=booking, actor=staff)


class TestCancellation:
    def test_an_early_cancellation_costs_nothing(self, player, ground, sport_format):
        """Well outside the turf's free window."""
        ground.turf.cancellation_free_hours = 2
        ground.turf.save(update_fields=["cancellation_free_hours"])
        booking = book(player, ground, sport_format, start=next_slot_start(hours_ahead=48))
        profile = get_or_create_profile(player)
        before = profile.reliability_score

        cancel_booking(booking=booking, actor=player, reason="Plans changed")

        booking.refresh_from_db()
        profile.refresh_from_db()
        assert booking.status == BookingStatus.CANCELLED
        assert booking.was_late_cancel is False
        assert profile.reliability_score == before

    def test_a_late_cancellation_costs_reliability(self, player, ground, sport_format):
        ground.turf.cancellation_free_hours = 48
        ground.turf.save(update_fields=["cancellation_free_hours"])
        booking = book(player, ground, sport_format, start=next_slot_start(hours_ahead=3))
        profile = get_or_create_profile(player)
        before = profile.reliability_score

        cancel_booking(booking=booking, actor=player)

        booking.refresh_from_db()
        profile.refresh_from_db()
        assert booking.was_late_cancel is True
        assert profile.reliability_score == before + settings.RELIABILITY_LATE_CANCEL_DELTA

    def test_a_turf_cancelling_late_does_not_punish_the_player(
        self, player, ground, sport_format, staff
    ):
        """The player did nothing wrong, and penalising them would be a reason to leave."""
        ground.turf.cancellation_free_hours = 48
        ground.turf.save(update_fields=["cancellation_free_hours"])
        booking = book(player, ground, sport_format, start=next_slot_start(hours_ahead=3))
        profile = get_or_create_profile(player)
        before = profile.reliability_score

        cancel_booking(booking=booking, actor=staff, reason="Flooding", by_staff=True)

        booking.refresh_from_db()
        profile.refresh_from_db()
        assert booking.was_late_cancel is False
        assert profile.reliability_score == before

    def test_cancelling_frees_the_slot(self, player, ground, sport_format):
        start = next_slot_start()
        booking = book(player, ground, sport_format, start=start)
        cancel_booking(booking=booking, actor=player)

        assert book(UserFactory(), ground, sport_format, start=start).pk is not None

    def test_the_reason_reaches_the_player(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        cancel_booking(booking=booking, actor=staff, reason="Pitch flooded", by_staff=True)

        booking.refresh_from_db()
        assert booking.cancel_reason == "Pitch flooded"
        assert Notification.objects.filter(
            user=player, kind=NotificationKind.BOOKING_CANCELLED
        ).exists()

    def test_is_late_cancellation_uses_the_turfs_window(self, player, ground, sport_format):
        ground.turf.cancellation_free_hours = 12
        ground.turf.save(update_fields=["cancellation_free_hours"])

        soon = book(player, ground, sport_format, start=next_slot_start(hours_ahead=6))
        assert is_late_cancellation(soon) is True

        cancel_booking(booking=soon, actor=player)
        later = book(player, ground, sport_format, start=next_slot_start(hours_ahead=72))
        assert is_late_cancellation(later) is False


class TestReliability:
    def test_it_is_clamped_to_the_ceiling(self):
        profile = get_or_create_profile(UserFactory())
        adjust_reliability(profile=profile, delta=50)
        assert profile.reliability_score == settings.RELIABILITY_MAX

    def test_it_cannot_go_below_zero(self):
        profile = get_or_create_profile(UserFactory())
        adjust_reliability(profile=profile, delta=-500)
        assert profile.reliability_score == 0

    @override_settings(RELIABILITY_NO_SHOW_DELTA=-30)
    def test_the_deltas_are_configurable(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        started = now() - timedelta(hours=2)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(started, started + timedelta(hours=1))
        )
        booking.refresh_from_db()
        profile = get_or_create_profile(player)
        before = profile.reliability_score

        mark_no_show(booking=booking, actor=staff)

        profile.refresh_from_db()
        assert profile.reliability_score == before - 30


class TestBatchJobs:
    def test_expiry_releases_only_overdue_reservations(self, player, ground, sport_format):
        overdue = book(player, ground, sport_format)
        Booking.objects.filter(pk=overdue.pk).update(expires_at=now() - timedelta(minutes=1))
        fresh = book(UserFactory(), ground, sport_format, start=next_slot_start(hours_ahead=48))

        assert expire_overdue_bookings() == 1

        overdue.refresh_from_db()
        fresh.refresh_from_db()
        assert overdue.status == BookingStatus.EXPIRED
        assert fresh.status == BookingStatus.RESERVED

    def test_expiry_leaves_confirmed_bookings_alone(self, player, ground, sport_format, staff):
        """A staff confirmation that lands a moment before the job runs must win."""
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        Booking.objects.filter(pk=booking.pk).update(expires_at=now() - timedelta(minutes=1))

        assert expire_overdue_bookings() == 0
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED

    def test_completion_closes_out_finished_paid_bookings(
        self, player, ground, sport_format, staff
    ):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(now() - timedelta(hours=2), now() - timedelta(hours=1))
        )

        assert complete_finished_bookings() == 1
        booking.refresh_from_db()
        assert booking.status == BookingStatus.COMPLETED

    def test_completion_ignores_unpaid_bookings(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(now() - timedelta(hours=2), now() - timedelta(hours=1))
        )

        assert complete_finished_bookings() == 0

    def test_completion_leaves_a_running_slot_alone(self, player, ground, sport_format, staff):
        booking = book(player, ground, sport_format)
        confirm_booking(booking=booking, actor=staff)
        mark_paid(booking=booking, actor=staff)
        Booking.objects.filter(pk=booking.pk).update(
            time_range=TimestamptzRange(
                now() - timedelta(minutes=10), now() + timedelta(minutes=50)
            )
        )

        assert complete_finished_bookings() == 0


def test_the_full_happy_path_leaves_a_readable_timeline(player, ground, sport_format, staff):
    """Acceptance: staff marks paid, it completes after the end time."""
    booking = book(player, ground, sport_format)
    confirm_booking(booking=booking, actor=staff)
    mark_paid(booking=booking, actor=staff)
    Booking.objects.filter(pk=booking.pk).update(
        time_range=TimestamptzRange(now() - timedelta(hours=2), now() - timedelta(hours=1))
    )
    booking.refresh_from_db()
    complete_booking(booking=booking)

    timeline = list(
        BookingEvent.objects.filter(booking=booking).values_list("to_status", flat=True)
    )
    assert timeline == ["reserved", "confirmed", "paid", "completed"]


def test_should_auto_confirm_needs_all_three_conditions(player, ground):
    turf = ground.turf
    assert should_auto_confirm(user=player, turf=turf) is False

    make_reliable(player)
    assert should_auto_confirm(user=player, turf=turf) is True

    turf.auto_confirm_enabled = False
    assert should_auto_confirm(user=player, turf=turf) is False
