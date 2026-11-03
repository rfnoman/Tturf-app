"""Stock, the counter and rentals (DOMAIN §9).

The test that matters most is `test_the_ledger_always_reconciles`: every other service
here is only trustworthy because the movements add up to the cached columns.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.inventory.models import CounterSale, MovementType, Rental, StockMovement
from apps.inventory.services import (
    OutOfStock,
    adjust_stock,
    commit_sale,
    get_or_create_item,
    ledger_totals,
    location_for_turf,
    low_stock_items,
    mark_rental_lost,
    receive_stock,
    record_counter_sale,
    release,
    rent_out,
    reserve,
    return_rental,
    void_counter_sale,
    warehouse,
)
from apps.notifications.models import Notification, NotificationKind

from .factories import reload, rental_product, stocked_turf

pytestmark = pytest.mark.django_db


class TestReceivingAndAdjusting:
    def test_receiving_stock_writes_a_movement(self):
        _turf, cashier, _product, item = stocked_turf(on_hand=0)
        receive_stock(item=item, quantity=24, actor=cashier, note="Friday delivery")

        item = reload(item)
        assert item.on_hand == 24
        movement = item.movements.get()
        assert movement.type == MovementType.PURCHASE
        assert movement.qty_delta == 24
        assert movement.note == "Friday delivery"

    def test_receiving_nothing_is_refused(self):
        _turf, _cashier, _product, item = stocked_turf()
        with pytest.raises(Exception, match="positive quantity"):
            receive_stock(item=item, quantity=0)

    def test_an_adjustment_needs_a_reason(self):
        _turf, _cashier, _product, item = stocked_turf()
        with pytest.raises(Exception, match="why"):
            adjust_stock(item=item, delta=-1, reason="  ")

    def test_an_adjustment_can_be_negative(self):
        _turf, cashier, _product, item = stocked_turf(on_hand=10)
        adjust_stock(item=item, delta=-3, reason="Three bottles burst", actor=cashier)

        assert reload(item).on_hand == 7

    def test_stock_cannot_go_negative(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=2)
        with pytest.raises(OutOfStock):
            adjust_stock(item=item, delta=-5, reason="Count")

        assert reload(item).on_hand == 2


class TestReservations:
    def test_reserving_holds_stock_without_removing_it(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=10)
        reserve(item=item, quantity=4, reference="order:abc")

        item = reload(item)
        assert item.on_hand == 10
        assert item.reserved == 4
        assert item.available == 6

    def test_cannot_reserve_more_than_is_available(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=3)
        with pytest.raises(OutOfStock):
            reserve(item=item, quantity=4)

        assert reload(item).reserved == 0

    def test_releasing_gives_it_back(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=10)
        reserve(item=item, quantity=4)
        release(item=item, quantity=4)

        assert reload(item).reserved == 0

    def test_cannot_release_more_than_is_held(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=10)
        reserve(item=item, quantity=2)
        with pytest.raises(Exception, match="more than is reserved"):
            release(item=item, quantity=3)

    def test_committing_a_sale_takes_both_columns_down(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=10)
        reserve(item=item, quantity=3, reference="order:abc")
        commit_sale(item=item, quantity=3, reference="order:abc")

        item = reload(item)
        assert (item.on_hand, item.reserved) == (7, 0)

    def test_cannot_commit_what_was_never_reserved(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=10)
        with pytest.raises(Exception, match="never reserved"):
            commit_sale(item=item, quantity=1)


class TestCounterSale:
    def test_selling_three_waters_drops_the_stock_by_three(self):
        """The phase's acceptance line, as a test."""
        turf, cashier, product, item = stocked_turf(on_hand=10, price="25.00")

        sale = record_counter_sale(
            turf=turf,
            staff=cashier,
            lines=[{"product": product, "quantity": 3}],
            cash_received=Decimal("100.00"),
        )

        assert reload(item).on_hand == 7
        assert sale.total == Decimal("75.00")
        assert sale.change_due == Decimal("25.00")
        assert item.movements.filter(type=MovementType.COUNTER_SALE).count() == 1

    def test_the_price_is_copied_onto_the_line(self):
        """A price rise next week must not rewrite last week's receipt."""
        turf, cashier, product, _item = stocked_turf(on_hand=10, price="25.00")
        sale = record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 2}]
        )

        product.base_price = Decimal("40.00")
        product.save(update_fields=["base_price"])

        assert sale.lines.get().unit_price == Decimal("25.00")
        assert sale.total == Decimal("50.00")

    def test_a_location_price_override_wins(self):
        turf, cashier, product, item = stocked_turf(on_hand=10, price="25.00")
        item.price_override = Decimal("30.00")
        item.save(update_fields=["price_override"])

        sale = record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 1}]
        )
        assert sale.total == Decimal("30.00")

    def test_somebody_elses_staff_cannot_sell_here(self):
        turf, _cashier, product, _item = stocked_turf()
        with pytest.raises(Exception, match="this turf's staff"):
            record_counter_sale(
                turf=turf, staff=UserFactory(), lines=[{"product": product, "quantity": 1}]
            )

    def test_an_empty_sale_is_refused(self):
        turf, cashier, _product, _item = stocked_turf()
        with pytest.raises(Exception, match="at least one item"):
            record_counter_sale(turf=turf, staff=cashier, lines=[])

    def test_selling_more_than_is_there_fails_and_changes_nothing(self):
        turf, cashier, product, item = stocked_turf(on_hand=2)
        with pytest.raises(OutOfStock):
            record_counter_sale(
                turf=turf, staff=cashier, lines=[{"product": product, "quantity": 5}]
            )

        assert reload(item).on_hand == 2
        assert CounterSale.objects.count() == 0

    def test_rental_gear_is_not_sold_at_the_counter(self):
        turf, cashier, _product, _item = stocked_turf()
        bibs, _bib_item = rental_product(turf)

        with pytest.raises(Exception, match="for rent"):
            record_counter_sale(turf=turf, staff=cashier, lines=[{"product": bibs, "quantity": 1}])

    def test_voiding_puts_the_stock_back_without_deleting_anything(self):
        turf, cashier, product, item = stocked_turf(on_hand=10)
        sale = record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 3}]
        )

        void_counter_sale(sale=sale, actor=cashier, reason="Rang up twice")

        assert reload(item).on_hand == 10
        sale.refresh_from_db()
        assert sale.status == CounterSale.Status.VOIDED
        # The original sale movement is still there: the ledger is append-only.
        assert item.movements.filter(type=MovementType.COUNTER_SALE).count() == 1

    def test_a_sale_cannot_be_voided_twice(self):
        turf, cashier, product, _item = stocked_turf(on_hand=10)
        sale = record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 1}]
        )
        void_counter_sale(sale=sale, actor=cashier)

        with pytest.raises(Exception, match="already been voided"):
            void_counter_sale(sale=sale, actor=cashier)


class TestRentals:
    def test_bibs_go_out_and_come_back(self):
        """The phase's acceptance line: tracked out, then returned."""
        turf, cashier, _product, _item = stocked_turf()
        bibs, bib_item = rental_product(turf, on_hand=3)
        player = UserFactory()

        rental = rent_out(turf=turf, product=bibs, player=player, quantity=1, actor=cashier)

        item = reload(bib_item)
        # Still the turf's, but spoken for.
        assert (item.on_hand, item.reserved, item.available) == (3, 1, 2)
        assert rental.status == Rental.Status.OUT
        assert rental.price == Decimal("150.00")
        assert rental.deposit == Decimal("500.00")

        return_rental(rental=rental, actor=cashier)

        item = reload(bib_item)
        assert (item.on_hand, item.reserved) == (3, 0)
        assert rental.returned_at is not None

    def test_gear_that_never_comes_back_leaves_stock(self):
        turf, cashier, _product, _item = stocked_turf()
        bibs, bib_item = rental_product(turf, on_hand=3)
        rental = rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier)

        mark_rental_lost(rental=rental, actor=cashier)

        item = reload(bib_item)
        assert (item.on_hand, item.reserved) == (2, 0)
        assert rental.status == Rental.Status.LOST
        assert rental.charges == Decimal("500.00")

    def test_cannot_rent_out_more_than_there_is(self):
        turf, cashier, _product, _item = stocked_turf()
        bibs, _bib_item = rental_product(turf, on_hand=1)
        rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier)

        with pytest.raises(OutOfStock):
            rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier)

    def test_a_sale_product_cannot_be_rented(self):
        turf, cashier, product, _item = stocked_turf()
        with pytest.raises(Exception, match="not rental gear"):
            rent_out(turf=turf, product=product, player=UserFactory(), actor=cashier)

    def test_only_a_rental_that_is_out_can_be_returned(self):
        turf, cashier, _product, _item = stocked_turf()
        bibs, _bib_item = rental_product(turf)
        rental = rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier)
        return_rental(rental=rental, actor=cashier)

        with pytest.raises(Exception, match="not out"):
            return_rental(rental=rental, actor=cashier)


class TestLowStock:
    def test_the_staff_are_told_when_something_runs_low(self):
        turf, cashier, product, item = stocked_turf(on_hand=6)
        item.low_stock_threshold = 3
        item.save(update_fields=["low_stock_threshold"])

        record_counter_sale(turf=turf, staff=cashier, lines=[{"product": product, "quantity": 4}])

        assert Notification.objects.filter(user=cashier, kind=NotificationKind.STOCK_LOW).exists()

    def test_a_full_shelf_says_nothing(self):
        turf, cashier, product, _item = stocked_turf(on_hand=50)
        record_counter_sale(turf=turf, staff=cashier, lines=[{"product": product, "quantity": 1}])
        assert Notification.objects.filter(kind=NotificationKind.STOCK_LOW).count() == 0

    def test_the_low_stock_list_is_what_the_dashboard_reads(self):
        turf, _cashier, _product, item = stocked_turf(on_hand=2)
        assert list(low_stock_items(location=location_for_turf(turf))) == [item]


class TestLedger:
    def test_the_ledger_always_reconciles(self):
        """`StockItem` is a cache of `StockMovement`; this is what makes that true.

        Everything a turf can do to one product, then the movements replayed and compared
        with the cached columns. If a service ever changes a quantity without writing its
        line, this is the test that fails.
        """
        turf, cashier, product, item = stocked_turf(on_hand=20)
        bibs, bib_item = rental_product(turf, on_hand=4)
        player = UserFactory()

        record_counter_sale(turf=turf, staff=cashier, lines=[{"product": product, "quantity": 3}])
        adjust_stock(item=item, delta=-2, reason="Two leaked", actor=cashier)
        reserve(item=item, quantity=5, reference="order:1")
        release(item=item, quantity=2, reference="order:1")
        commit_sale(item=item, quantity=3, reference="order:1")
        receive_stock(item=item, quantity=12, actor=cashier)

        out = rent_out(turf=turf, product=bibs, player=player, actor=cashier)
        return_rental(rental=out, actor=cashier)
        lost = rent_out(turf=turf, product=bibs, player=player, actor=cashier)
        mark_rental_lost(rental=lost, actor=cashier)

        for row in (reload(item), reload(bib_item)):
            on_hand, reserved = ledger_totals(row)
            assert (row.on_hand, row.reserved) == (on_hand, reserved)

    def test_every_movement_says_what_caused_it(self):
        turf, cashier, product, item = stocked_turf(on_hand=10)
        sale = record_counter_sale(
            turf=turf, staff=cashier, lines=[{"product": product, "quantity": 1}]
        )

        movement = item.movements.get(type=MovementType.COUNTER_SALE)
        assert movement.reference == f"counter_sale:{sale.id}"
        assert movement.actor == cashier

    def test_a_failed_operation_leaves_no_trace(self):
        _turf, _cashier, _product, item = stocked_turf(on_hand=1)
        before = StockMovement.objects.count()

        with pytest.raises(OutOfStock):
            reserve(item=item, quantity=99)

        assert StockMovement.objects.count() == before


class TestLocations:
    def test_a_turf_gets_one_location(self):
        turf, _cashier, _product, _item = stocked_turf()
        assert location_for_turf(turf) == location_for_turf(turf)

    def test_the_warehouse_is_a_singleton(self):
        assert warehouse() == warehouse()

    def test_the_same_product_at_two_locations_is_two_items(self):
        turf, _cashier, product, item = stocked_turf()
        other = get_or_create_item(location=warehouse(), product=product)

        assert other != item
        assert other.on_hand == 0
