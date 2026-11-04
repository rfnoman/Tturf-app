"""Checkout, the order lifecycle and what happens to stock (DOMAIN §9)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings

from apps.accounts.tests.factories import UserFactory
from apps.inventory.models import MovementType
from apps.inventory.services import OutOfStock, ledger_totals
from apps.notifications.models import Notification, NotificationKind
from apps.payments.models import Payment, PaymentStatus
from apps.store.models import Fulfilment, Order, OrderStatus
from apps.store.services import (
    accept_order,
    add_to_cart,
    assign_rider,
    cancel_order,
    cart_by_source,
    checkout,
    clear_cart,
    get_cart,
    mark_out_for_delivery,
    mark_ready_for_pickup,
    pack_order,
    set_cart_quantity,
    settle_order,
)

from .factories import address_for, dhaka_zone, match_in, platform_product, turf_shelf

pytestmark = pytest.mark.django_db

CUTOFF = int(settings.TURF_DELIVERY_CUTOFF_HOURS)


def rider_for(zone=None):
    from apps.store.models import RiderProfile

    rider = RiderProfile.objects.create(user=UserFactory(), phone="+8801711111111")
    if zone:
        rider.zones.add(zone)
    return rider


class TestCart:
    def test_adding_the_same_thing_twice_adds_up(self):
        _product, item = platform_product(on_hand=10)
        player = UserFactory()

        add_to_cart(user=player, stock_item=item, quantity=2)
        line = add_to_cart(user=player, stock_item=item, quantity=3)

        assert line.quantity == 5
        assert get_cart(player).items.count() == 1

    def test_the_cart_will_not_hold_more_than_the_shelf(self):
        _product, item = platform_product(on_hand=2)
        player = UserFactory()

        with pytest.raises(OutOfStock):
            add_to_cart(user=player, stock_item=item, quantity=3)

    def test_nothing_is_held_until_checkout(self):
        """A cart is a list, not a promise — two shoppers may both hold the last one."""
        _product, item = platform_product(on_hand=1)
        add_to_cart(user=UserFactory(), stock_item=item)
        add_to_cart(user=UserFactory(), stock_item=item)

        item.refresh_from_db()
        assert item.reserved == 0

    def test_setting_a_quantity_to_zero_removes_the_line(self):
        _product, item = platform_product()
        player = UserFactory()
        add_to_cart(user=player, stock_item=item, quantity=2)

        assert set_cart_quantity(user=player, stock_item=item, quantity=0) is None
        assert get_cart(player).items.count() == 0

    def test_rental_gear_cannot_be_ordered(self):
        from apps.inventory.models import ProductKind

        _turf, _cashier, product, item = turf_shelf(name="Bibs", category="rental")
        product.kind = ProductKind.RENTAL
        product.save(update_fields=["kind"])

        with pytest.raises(Exception, match="arranged at the turf"):
            add_to_cart(user=UserFactory(), stock_item=item)

    def test_the_cart_groups_by_source(self):
        _product, warehouse_item = platform_product()
        _turf, _cashier, _turf_product, turf_item = turf_shelf()
        player = UserFactory()

        add_to_cart(user=player, stock_item=warehouse_item)
        add_to_cart(user=player, stock_item=turf_item)

        groups = cart_by_source(user=player)
        assert len(groups) == 2

    def test_clearing_empties_it(self):
        _product, item = platform_product()
        player = UserFactory()
        add_to_cart(user=player, stock_item=item)

        clear_cart(user=player)
        assert get_cart(player).items.count() == 0


class TestCheckout:
    def test_a_cart_from_two_sources_becomes_two_orders(self):
        """DOMAIN §9: one order, one stock source."""
        _product, warehouse_item = platform_product(price="4200.00")
        turf, _cashier, _turf_product, turf_item = turf_shelf(price="15.00")
        player = UserFactory()
        dhaka_zone()
        address = address_for(player)

        add_to_cart(user=player, stock_item=warehouse_item, quantity=1)
        add_to_cart(user=player, stock_item=turf_item, quantity=4)

        orders = checkout(
            user=player,
            choices={
                str(warehouse_item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                    "address": address,
                },
                str(turf_item.location_id): {"fulfilment": Fulfilment.PICKUP_AT_TURF},
            },
        )

        assert len(orders) == 2
        delivery = next(order for order in orders if order.is_delivery)
        pickup = next(order for order in orders if not order.is_delivery)

        assert delivery.subtotal == Decimal("4200.00")
        assert delivery.delivery_fee == Decimal("60.00")
        assert delivery.total == Decimal("4260.00")
        assert pickup.total == Decimal("60.00")
        assert get_cart(player).items.count() == 0

    def test_checkout_holds_the_stock(self):
        _product, item = platform_product(on_hand=10)
        player = UserFactory()
        dhaka_zone()
        add_to_cart(user=player, stock_item=item, quantity=3)

        checkout(
            user=player,
            choices={
                str(item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                    "address": address_for(player),
                }
            },
        )

        item.refresh_from_db()
        assert (item.on_hand, item.reserved, item.available) == (10, 3, 7)

    def test_the_line_keeps_the_price_and_the_nutrition_it_was_bought_at(self):
        product, item = platform_product(price="220.00", calories=230, protein_g=Decimal("20.0"))
        player = UserFactory()
        dhaka_zone()
        add_to_cart(user=player, stock_item=item)

        order = checkout(
            user=player,
            choices={
                str(item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                    "address": address_for(player),
                }
            },
        )[0]

        product.base_price = Decimal("500.00")
        product.calories = 999
        product.save()

        line = order.items.get()
        assert line.unit_price == Decimal("220.00")
        assert line.nutrition["calories"] == 230
        assert line.nutrition["protein_g"] == "20.0"

    def test_an_option_the_matrix_refuses_is_refused_here_too(self):
        _turf, _cashier, _product, item = turf_shelf()
        player = UserFactory()
        add_to_cart(user=player, stock_item=item)

        with pytest.raises(Exception, match="does not deliver"):
            checkout(
                user=player,
                choices={
                    str(item.location_id): {
                        "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                        "address": address_for(player),
                    }
                },
            )

    def test_a_second_order_failing_rolls_the_first_one_back(self):
        """All or nothing: half an order is worse than none."""
        _product, warehouse_item = platform_product(on_hand=10)
        _turf, _cashier, _turf_product, turf_item = turf_shelf(on_hand=1)
        player = UserFactory()
        dhaka_zone()

        add_to_cart(user=player, stock_item=warehouse_item, quantity=2)
        add_to_cart(user=player, stock_item=turf_item, quantity=1)
        # Somebody else takes the turf's last one between adding and paying.
        from apps.inventory.services import adjust_stock

        adjust_stock(item=turf_item, delta=-1, reason="Sold at the counter")

        with pytest.raises(OutOfStock):
            checkout(
                user=player,
                choices={
                    str(warehouse_item.location_id): {
                        "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                        "address": address_for(player),
                    },
                    str(turf_item.location_id): {"fulfilment": Fulfilment.PICKUP_AT_TURF},
                },
            )

        assert Order.objects.count() == 0
        warehouse_item.refresh_from_db()
        assert warehouse_item.reserved == 0
        # The cart is untouched, so the player can fix it rather than start again.
        assert get_cart(player).items.count() == 2

    def test_an_empty_cart_cannot_be_checked_out(self):
        with pytest.raises(Exception, match="empty"):
            checkout(user=UserFactory(), choices={})

    def test_a_source_with_no_choice_is_refused(self):
        _product, item = platform_product()
        player = UserFactory()
        add_to_cart(user=player, stock_item=item)

        with pytest.raises(Exception, match="Choose how"):
            checkout(user=player, choices={})

    def test_an_order_to_a_turf_carries_the_kick_off_time(self):
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(CUTOFF + 6, player=player)
        add_to_cart(user=player, stock_item=item)

        order = checkout(
            user=player,
            choices={
                str(item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_TURF,
                    "match": match,
                }
            },
        )[0]

        assert order.match == match
        assert order.scheduled_for == match.starts_at

    def test_the_source_is_told_about_a_new_order(self):
        _turf, cashier, _product, item = turf_shelf()
        player = UserFactory()
        add_to_cart(user=player, stock_item=item)

        checkout(
            user=player,
            choices={str(item.location_id): {"fulfilment": Fulfilment.PICKUP_AT_TURF}},
        )

        assert Notification.objects.filter(
            user=cashier, kind=NotificationKind.ORDER_PLACED
        ).exists()


def place_pickup_order(*, on_hand=10, quantity=2):
    turf, cashier, _product, item = turf_shelf(on_hand=on_hand, price="25.00")
    player = UserFactory()
    add_to_cart(user=player, stock_item=item, quantity=quantity)
    order = checkout(
        user=player,
        choices={str(item.location_id): {"fulfilment": Fulfilment.PICKUP_AT_TURF}},
    )[0]
    return turf, cashier, player, item, order


class TestLifecycle:
    def test_accept_then_ready_then_picked_up_commits_the_stock(self):
        _turf, cashier, player, item, order = place_pickup_order(on_hand=10, quantity=2)

        accept_order(order=order, actor=cashier)
        mark_ready_for_pickup(order=order, actor=cashier)
        settle_order(order=order, actor=cashier)

        item.refresh_from_db()
        assert (item.on_hand, item.reserved) == (8, 0)
        assert order.status == OrderStatus.PICKED_UP
        assert order.settled_at is not None
        assert item.movements.filter(type=MovementType.SALE).count() == 1

    def test_settling_records_the_cash(self):
        _turf, cashier, _player, _item, order = place_pickup_order()

        settle_order(order=order, actor=cashier, cash_received=Decimal("100.00"))

        payment = Payment.objects.get(order=order)
        assert payment.amount == order.total
        assert payment.status == PaymentStatus.PAID
        assert payment.collected_by == cashier

    def test_the_player_is_told_at_each_step(self):
        _turf, cashier, player, _item, order = place_pickup_order()

        accept_order(order=order, actor=cashier)
        mark_ready_for_pickup(order=order, actor=cashier)
        settle_order(order=order, actor=cashier)

        kinds = set(Notification.objects.filter(user=player).values_list("kind", flat=True))
        assert {
            NotificationKind.ORDER_ACCEPTED,
            NotificationKind.ORDER_READY,
            NotificationKind.ORDER_DELIVERED,
        } <= kinds

    def test_cancelling_gives_the_stock_back(self):
        _turf, _cashier, player, item, order = place_pickup_order(on_hand=10, quantity=3)

        cancel_order(order=order, actor=player, reason="Changed my mind")

        item.refresh_from_db()
        assert (item.on_hand, item.reserved) == (10, 0)
        assert order.status == OrderStatus.CANCELLED

    def test_a_player_cannot_cancel_once_it_is_packed(self):
        _turf, cashier, player, _item, order = place_pickup_order()
        pack_order(order=order, actor=cashier)

        with pytest.raises(Exception, match="already being prepared"):
            cancel_order(order=order, actor=player)

    def test_the_turf_can_still_cancel_a_packed_order(self):
        _turf, cashier, _player, item, order = place_pickup_order(quantity=2)
        pack_order(order=order, actor=cashier)

        cancel_order(order=order, actor=cashier, reason="We dropped it")

        item.refresh_from_db()
        assert item.reserved == 0

    def test_a_stranger_cannot_touch_somebody_elses_order(self):
        _turf, _cashier, _player, _item, order = place_pickup_order()

        with pytest.raises(Exception, match="Only the source"):
            accept_order(order=order, actor=UserFactory())

    def test_a_finished_order_cannot_be_cancelled(self):
        _turf, cashier, player, _item, order = place_pickup_order()
        settle_order(order=order, actor=cashier)

        with pytest.raises(Exception, match="already finished"):
            cancel_order(order=order, actor=player)

    def test_the_ledger_still_reconciles_through_a_whole_order(self):
        _turf, cashier, _player, item, order = place_pickup_order(on_hand=12, quantity=5)
        accept_order(order=order, actor=cashier)
        settle_order(order=order, actor=cashier)

        item.refresh_from_db()
        on_hand, reserved = ledger_totals(item)
        assert (item.on_hand, item.reserved) == (on_hand, reserved)

    def test_a_pickup_is_never_out_for_delivery(self):
        _turf, cashier, _player, _item, order = place_pickup_order()
        with pytest.raises(Exception, match="never out for delivery"):
            mark_out_for_delivery(order=order, actor=cashier)

    def test_the_order_keeps_its_history(self):
        _turf, cashier, _player, _item, order = place_pickup_order()
        accept_order(order=order, actor=cashier)
        mark_ready_for_pickup(order=order, actor=cashier)

        assert list(order.events.values_list("to_status", flat=True)) == [
            OrderStatus.PLACED,
            OrderStatus.ACCEPTED,
            OrderStatus.READY_FOR_PICKUP,
        ]


class TestDelivery:
    def place_delivery_order(self):
        _product, item = platform_product(on_hand=10, price="220.00")
        player = UserFactory()
        zone = dhaka_zone(fee="60.00")
        add_to_cart(user=player, stock_item=item, quantity=2)
        order = checkout(
            user=player,
            choices={
                str(item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                    "address": address_for(player),
                }
            },
        )[0]
        return item, player, zone, order

    def test_a_rider_delivers_and_the_stock_is_committed(self):
        item, _player, zone, order = self.place_delivery_order()
        admin = UserFactory(is_platform_admin=True)
        rider = rider_for(zone)

        accept_order(order=order, actor=admin)
        assign_rider(order=order, rider=rider, actor=admin)
        mark_out_for_delivery(order=order, actor=rider.user)
        settle_order(order=order, actor=rider.user)

        item.refresh_from_db()
        assert (item.on_hand, item.reserved) == (8, 0)
        assert order.status == OrderStatus.DELIVERED
        assert Payment.objects.filter(order=order).exists()

    def test_a_rider_is_told_about_their_delivery(self):
        _item, _player, zone, order = self.place_delivery_order()
        admin = UserFactory(is_platform_admin=True)
        rider = rider_for(zone)

        assign_rider(order=order, rider=rider, actor=admin)

        assert Notification.objects.filter(
            user=rider.user, kind=NotificationKind.ORDER_ASSIGNED
        ).exists()

    def test_a_rider_cannot_settle_an_order_that_is_not_theirs(self):
        _item, _player, zone, order = self.place_delivery_order()
        other = rider_for(zone)

        with pytest.raises(Exception, match="Only the source or the rider"):
            settle_order(order=order, actor=other.user)

    def test_a_pickup_needs_no_rider(self):
        _turf, cashier, _player, _item, order = place_pickup_order()
        with pytest.raises(Exception, match="pickup does not need a rider"):
            assign_rider(order=order, rider=rider_for(), actor=cashier)
