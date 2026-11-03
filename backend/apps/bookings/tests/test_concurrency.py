"""The exclusion constraint, exercised for real (phase 03 step 5).

The phase brief asks for "two parallel bookings for the same slot — exactly one
succeeds". That cannot be tested with ordinary `pytest.mark.django_db`, which wraps each
test in a transaction and gives every thread the same connection. These tests use
``django_db(transaction=True)`` and real threads, so Postgres genuinely arbitrates.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import IntegrityError, connections, transaction
from psycopg.types.range import TimestamptzRange

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import ACTIVE_BOOKING_STATUSES, Booking, BookingStatus
from apps.bookings.services import SlotTakenError, create_booking

from .factories import bookable_ground, next_slot_start

#: Real threads need real connections, so these cannot run inside the usual per-test
#: transaction.
pytestmark = pytest.mark.django_db(transaction=True)


def test_two_threads_booking_the_same_slot_leave_exactly_one_winner():
    """Acceptance: one succeeds, the other is told the slot was just taken."""
    ground, sport_format = bookable_ground()
    start = next_slot_start()
    players = [UserFactory(), UserFactory()]
    results: list = []
    barrier = threading.Barrier(len(players))

    def book(user):
        try:
            # Line the threads up so they really do race for the same slot.
            barrier.wait(timeout=10)
            results.append(
                create_booking(user=user, ground=ground, start=start, sport_format=sport_format)
            )
        except Exception as exc:
            results.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=book, args=(user,)) for user in players]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    bookings = [r for r in results if isinstance(r, Booking)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(bookings) == 1, f"expected one winner, got {results}"
    assert len(failures) == 1
    assert isinstance(failures[0], SlotTakenError)
    assert Booking.objects.filter(ground=ground, status__in=ACTIVE_BOOKING_STATUSES).count() == 1


def test_ten_threads_still_leave_exactly_one_winner():
    """The constraint, not luck: more contention must not produce more winners."""
    ground, sport_format = bookable_ground()
    start = next_slot_start()
    players = [UserFactory() for _ in range(10)]
    results: list = []
    barrier = threading.Barrier(len(players))

    def book(user):
        try:
            barrier.wait(timeout=15)
            results.append(
                create_booking(user=user, ground=ground, start=start, sport_format=sport_format)
            )
        except Exception as exc:
            results.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=book, args=(user,)) for user in players]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len([r for r in results if isinstance(r, Booking)]) == 1
    assert all(isinstance(r, SlotTakenError) for r in results if not isinstance(r, Booking))


def test_the_constraint_rejects_an_overlapping_insert_outright():
    """Belt and braces: the database refuses it even with the services bypassed."""
    ground, sport_format = bookable_ground()
    start = next_slot_start()

    Booking.objects.create(
        ground=ground,
        booked_by=UserFactory(),
        sport=sport_format.sport,
        sport_format=sport_format,
        time_range=TimestamptzRange(start, start + timedelta(hours=1)),
        price="2000.00",
        status=BookingStatus.CONFIRMED,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            ground=ground,
            booked_by=UserFactory(),
            sport=sport_format.sport,
            sport_format=sport_format,
            # Overlaps by half an hour, which is enough.
            time_range=TimestamptzRange(
                start + timedelta(minutes=30), start + timedelta(minutes=90)
            ),
            price="2000.00",
            status=BookingStatus.RESERVED,
        )


def test_back_to_back_slots_do_not_collide():
    """The range is half-open, which is what makes consecutive hours bookable."""
    ground, sport_format = bookable_ground()
    start = next_slot_start()

    first = Booking.objects.create(
        ground=ground,
        booked_by=UserFactory(),
        sport=sport_format.sport,
        sport_format=sport_format,
        time_range=TimestamptzRange(start, start + timedelta(hours=1)),
        price="2000.00",
        status=BookingStatus.CONFIRMED,
    )
    second = Booking.objects.create(
        ground=ground,
        booked_by=UserFactory(),
        sport=sport_format.sport,
        sport_format=sport_format,
        time_range=TimestamptzRange(start + timedelta(hours=1), start + timedelta(hours=2)),
        price="2000.00",
        status=BookingStatus.CONFIRMED,
    )

    assert first.pk != second.pk


def test_a_cancelled_booking_frees_its_slot_immediately():
    """The constraint only covers the statuses that hold a slot."""
    ground, sport_format = bookable_ground()
    start = next_slot_start()

    Booking.objects.create(
        ground=ground,
        booked_by=UserFactory(),
        sport=sport_format.sport,
        sport_format=sport_format,
        time_range=TimestamptzRange(start, start + timedelta(hours=1)),
        price="2000.00",
        status=BookingStatus.CANCELLED,
    )

    taken = create_booking(
        user=UserFactory(), ground=ground, start=start, sport_format=sport_format
    )
    assert taken.pk is not None


def test_the_same_slot_on_another_ground_is_free():
    """The constraint is per ground, not per turf."""
    ground, sport_format = bookable_ground()
    other, other_format = bookable_ground()
    start = next_slot_start()

    create_booking(user=UserFactory(), ground=ground, start=start, sport_format=sport_format)
    create_booking(user=UserFactory(), ground=other, start=start, sport_format=other_format)

    assert Booking.objects.count() == 2
