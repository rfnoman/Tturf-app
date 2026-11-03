"""Reserving under contention (phase 07 step 5).

The phase asks that "reserving more than available fails even with parallel requests".
`select_for_update` is only a claim until threads on real connections try to break it, so
these tests use `django_db(transaction=True)` and let Postgres arbitrate.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connections

from apps.inventory.models import StockItem
from apps.inventory.services import (
    OutOfStock,
    ledger_totals,
    record_counter_sale,
    reserve,
)

from .factories import stocked_turf

pytestmark = pytest.mark.django_db(transaction=True)


def run_in_threads(work, count: int):
    """Line `count` threads up on a barrier and run `work(index)` in each."""
    results: list = []
    barrier = threading.Barrier(count)

    def runner(index):
        try:
            barrier.wait(timeout=15)
            results.append(work(index))
        except Exception as exc:
            results.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_three_threads_cannot_reserve_the_last_two_items():
    """Two succeed, the third is told there is nothing left — never a negative shelf."""
    _turf, _cashier, _product, item = stocked_turf(on_hand=2)

    results = run_in_threads(
        lambda index: reserve(item=item, quantity=1, reference=f"order:{index}"), 3
    )

    succeeded = [r for r in results if isinstance(r, StockItem)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(succeeded) == 2, f"expected two winners, got {results}"
    assert all(isinstance(failure, OutOfStock) for failure in failures)

    item.refresh_from_db()
    assert (item.on_hand, item.reserved, item.available) == (2, 2, 0)


def test_ten_threads_against_four_items_leave_exactly_four_reservations():
    """More contention must not produce more stock."""
    _turf, _cashier, _product, item = stocked_turf(on_hand=4)

    results = run_in_threads(
        lambda index: reserve(item=item, quantity=1, reference=f"order:{index}"), 10
    )

    assert len([r for r in results if isinstance(r, StockItem)]) == 4
    item.refresh_from_db()
    assert item.reserved == 4
    assert item.available == 0


def test_parallel_counter_sales_never_oversell():
    """Two cashiers on two tablets, one bottle left."""
    turf, cashier, product, item = stocked_turf(on_hand=1)

    results = run_in_threads(
        lambda _index: record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 1}]
        ),
        4,
    )

    assert len([r for r in results if isinstance(r, Exception)]) == 3
    item.refresh_from_db()
    assert item.on_hand == 0


def test_the_ledger_still_reconciles_after_a_race():
    """A failed thread must leave no half-written movement behind."""
    _turf, _cashier, _product, item = stocked_turf(on_hand=3)

    run_in_threads(lambda index: reserve(item=item, quantity=1, reference=f"o:{index}"), 8)

    item.refresh_from_db()
    on_hand, reserved = ledger_totals(item)
    assert (item.on_hand, item.reserved) == (on_hand, reserved)
