"""Store endpoints: shopping, the cart, checkout and the queues."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.store.models import Fulfilment, OrderStatus, RiderProfile
from apps.store.services import add_to_cart, checkout

from .factories import address_for, dhaka_zone, match_in, platform_product, turf_shelf

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


class TestShopping:
    def test_the_store_needs_signing_in(self, client):
        assert client.get("/api/v1/store/home").status_code == 401

    def test_the_home_leads_with_the_players_next_match(self, client):
        _product, _item = platform_product()
        player = UserFactory()
        match = match_in(30, player=player)
        client.force_authenticate(player)

        response = client.get("/api/v1/store/home")

        assert response.status_code == 200
        assert response.data["match"]["id"] == str(match.id)
        assert response.data["match"]["turf_name"] == match.turf.name

    def test_a_player_with_no_match_still_gets_a_store(self, client):
        platform_product()
        client.force_authenticate(UserFactory())

        response = client.get("/api/v1/store/home")

        assert response.data["match"] is None
        assert response.data["platform_source_id"]

    def test_platform_items_are_listed(self, client):
        product, _item = platform_product(name="Whey protein")
        client.force_authenticate(UserFactory())

        rows = client.get("/api/v1/store/items", {"source": "platform"}).data

        assert [row["product"]["name"] for row in rows] == ["Whey protein"]
        assert rows[0]["available"] == 20

    def test_items_with_no_stock_are_not_offered(self, client):
        platform_product(name="Sold out", on_hand=0)
        client.force_authenticate(UserFactory())

        assert client.get("/api/v1/store/items", {"source": "platform"}).data == []

    def test_the_fitness_filters_work(self, client):
        platform_product(name="Protein bar", calories=230, protein_g=Decimal("20.0"))
        platform_product(name="Cola", calories=400, protein_g=Decimal("0.0"), category="drinks")
        client.force_authenticate(UserFactory())

        lean = client.get("/api/v1/store/items", {"source": "platform", "max_calories": 300}).data
        protein = client.get("/api/v1/store/items", {"source": "platform", "min_protein": 10}).data

        assert [row["product"]["name"] for row in lean] == ["Protein bar"]
        assert [row["product"]["name"] for row in protein] == ["Protein bar"]

    def test_a_turfs_shelf_is_shoppable_too(self, client):
        turf, _cashier, _product, item = turf_shelf(name="Banana")
        client.force_authenticate(UserFactory())

        rows = client.get("/api/v1/store/items", {"source": str(item.location_id)}).data

        assert rows[0]["product"]["name"] == "Banana"
        assert rows[0]["turf_slug"] == turf.slug


class TestCartApi:
    def test_adding_and_changing_a_line(self, client):
        _product, item = platform_product(price="220.00", on_hand=10)
        player = UserFactory()
        client.force_authenticate(player)

        added = client.post(
            "/api/v1/store/cart",
            {"stock_item_id": str(item.id), "quantity": 2},
            format="json",
        )
        assert added.status_code == 200
        assert added.data["item_count"] == 2
        assert Decimal(added.data["subtotal"]) == Decimal("440.00")

        changed = client.patch(
            "/api/v1/store/cart",
            {"stock_item_id": str(item.id), "quantity": 1},
            format="json",
        )
        assert changed.data["item_count"] == 1

    def test_removing_a_line(self, client):
        _product, item = platform_product()
        client.force_authenticate(UserFactory())
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")

        emptied = client.patch(
            "/api/v1/store/cart",
            {"stock_item_id": str(item.id), "quantity": 0},
            format="json",
        )
        assert emptied.data["groups"] == []

    def test_asking_for_more_than_there_is_conflicts(self, client):
        _product, item = platform_product(on_hand=1)
        client.force_authenticate(UserFactory())

        response = client.post(
            "/api/v1/store/cart",
            {"stock_item_id": str(item.id), "quantity": 5},
            format="json",
        )
        assert response.status_code == 409

    def test_the_cart_explains_every_option(self, client):
        _product, item = platform_product()
        player = UserFactory()
        client.force_authenticate(player)
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")

        group = client.get("/api/v1/store/cart").data["groups"][0]
        kinds = {option["kind"]: option for option in group["options"]}

        assert kinds[Fulfilment.PICKUP_AT_TURF]["available"] is False
        assert kinds[Fulfilment.PICKUP_AT_TURF]["reason"]
        assert kinds[Fulfilment.DELIVER_TO_ADDRESS]["available"] is False

    def test_an_address_prices_the_delivery(self, client):
        _product, item = platform_product()
        player = UserFactory()
        dhaka_zone(fee="60.00")
        address = address_for(player)
        client.force_authenticate(player)
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")

        group = client.get("/api/v1/store/cart", {"address": str(address.id)}).data["groups"][0]
        option = next(
            option for option in group["options"] if option["kind"] == Fulfilment.DELIVER_TO_ADDRESS
        )

        assert option["available"] is True
        assert Decimal(option["fee"]) == Decimal("60.00")

    def test_one_players_cart_is_not_anothers(self, client):
        _product, item = platform_product()
        mine = UserFactory()
        client.force_authenticate(mine)
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")

        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/store/cart").data["item_count"] == 0


class TestCheckoutApi:
    def test_checkout_splits_by_source(self, client):
        _product, warehouse_item = platform_product(price="4200.00")
        _turf, _cashier, _turf_product, turf_item = turf_shelf(price="15.00")
        player = UserFactory()
        dhaka_zone()
        address = address_for(player)
        client.force_authenticate(player)

        client.post("/api/v1/store/cart", {"stock_item_id": str(warehouse_item.id)}, format="json")
        client.post(
            "/api/v1/store/cart",
            {"stock_item_id": str(turf_item.id), "quantity": 2},
            format="json",
        )

        response = client.post(
            "/api/v1/store/checkout",
            {
                "choices": [
                    {
                        "source_id": str(warehouse_item.location_id),
                        "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                        "address_id": str(address.id),
                    },
                    {
                        "source_id": str(turf_item.location_id),
                        "fulfilment": Fulfilment.PICKUP_AT_TURF,
                    },
                ]
            },
            format="json",
        )

        assert response.status_code == 201
        assert len(response.data) == 2

    def test_a_refused_option_explains_itself(self, client):
        _turf, _cashier, _product, item = turf_shelf()
        player = UserFactory()
        dhaka_zone()
        address = address_for(player)
        client.force_authenticate(player)
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")

        response = client.post(
            "/api/v1/store/checkout",
            {
                "choices": [
                    {
                        "source_id": str(item.location_id),
                        "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                        "address_id": str(address.id),
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == 400
        assert "deliver" in str(response.data).lower()

    def test_addresses_are_private(self, client):
        _product, item = platform_product()
        stranger = UserFactory()
        owner = UserFactory()
        dhaka_zone()
        address = address_for(owner)

        client.force_authenticate(stranger)
        client.post("/api/v1/store/cart", {"stock_item_id": str(item.id)}, format="json")
        response = client.post(
            "/api/v1/store/checkout",
            {
                "choices": [
                    {
                        "source_id": str(item.location_id),
                        "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                        "address_id": str(address.id),
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == 404


def place_turf_order(client, *, quantity=2):
    turf, cashier, _product, item = turf_shelf(price="25.00", on_hand=10)
    player = UserFactory()
    add_to_cart(user=player, stock_item=item, quantity=quantity)
    order = checkout(
        user=player,
        choices={str(item.location_id): {"fulfilment": Fulfilment.PICKUP_AT_TURF}},
    )[0]
    return turf, cashier, player, item, order


class TestOrderApi:
    def test_a_player_sees_their_own_orders(self, client):
        _turf, _cashier, player, _item, order = place_turf_order(client)
        client.force_authenticate(player)

        rows = client.get("/api/v1/me/orders").data
        assert [row["id"] for row in rows] == [str(order.id)]

    def test_somebody_elses_order_is_not_found(self, client):
        _turf, _cashier, _player, _item, order = place_turf_order(client)
        client.force_authenticate(UserFactory())

        assert client.get(f"/api/v1/orders/{order.id}").status_code == 403

    def test_the_turf_queue_shows_incoming_orders(self, client):
        turf, cashier, _player, _item, _order = place_turf_order(client)
        client.force_authenticate(cashier)

        rows = client.get(f"/api/v1/me/turfs/{turf.slug}/orders").data
        assert len(rows) == 1
        assert rows[0]["status"] == OrderStatus.PLACED

    def test_staff_accept_and_settle_an_order(self, client):
        _turf, cashier, _player, item, order = place_turf_order(client, quantity=3)
        client.force_authenticate(cashier)

        assert (
            client.post(f"/api/v1/orders/{order.id}/accept", {}, format="json").status_code == 200
        )
        ready = client.post(f"/api/v1/orders/{order.id}/ready", {}, format="json")
        assert ready.data["status"] == OrderStatus.READY_FOR_PICKUP

        settled = client.post(
            f"/api/v1/orders/{order.id}/settle", {"cash_received": "100.00"}, format="json"
        )
        assert settled.data["status"] == OrderStatus.PICKED_UP

        item.refresh_from_db()
        assert item.on_hand == 7

    def test_a_player_cancels_their_own_order(self, client):
        _turf, _cashier, player, item, order = place_turf_order(client, quantity=2)
        client.force_authenticate(player)

        response = client.post(
            f"/api/v1/orders/{order.id}/cancel", {"reason": "Changed my mind"}, format="json"
        )

        assert response.data["status"] == OrderStatus.CANCELLED
        item.refresh_from_db()
        assert item.reserved == 0

    def test_the_platform_queue_is_admin_only(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/admin/orders").status_code == 403

    def test_a_rider_sees_only_their_own_deliveries(self, client):
        _product, item = platform_product()
        player = UserFactory()
        zone = dhaka_zone()
        address = address_for(player)
        add_to_cart(user=player, stock_item=item)
        order = checkout(
            user=player,
            choices={
                str(item.location_id): {
                    "fulfilment": Fulfilment.DELIVER_TO_ADDRESS,
                    "address": address,
                }
            },
        )[0]

        rider = RiderProfile.objects.create(user=UserFactory())
        rider.zones.add(zone)
        other_rider = RiderProfile.objects.create(user=UserFactory())

        admin = UserFactory(is_platform_admin=True)
        client.force_authenticate(admin)
        client.post(f"/api/v1/orders/{order.id}/rider", {"rider_id": str(rider.id)}, format="json")

        client.force_authenticate(rider.user)
        assert len(client.get("/api/v1/me/deliveries").data) == 1

        client.force_authenticate(other_rider.user)
        assert client.get("/api/v1/me/deliveries").data == []

    def test_a_rider_delivers(self, client):
        _product, item = platform_product(on_hand=5)
        player = UserFactory()
        zone = dhaka_zone()
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
        rider = RiderProfile.objects.create(user=UserFactory())
        rider.zones.add(zone)

        client.force_authenticate(UserFactory(is_platform_admin=True))
        client.post(f"/api/v1/orders/{order.id}/rider", {"rider_id": str(rider.id)}, format="json")

        client.force_authenticate(rider.user)
        client.post(f"/api/v1/orders/{order.id}/out", {}, format="json")
        settled = client.post(f"/api/v1/orders/{order.id}/settle", {}, format="json")

        assert settled.data["status"] == OrderStatus.DELIVERED
        item.refresh_from_db()
        assert item.on_hand == 3

    def test_an_order_carries_its_timeline(self, client):
        _turf, cashier, _player, _item, order = place_turf_order(client)
        client.force_authenticate(cashier)
        client.post(f"/api/v1/orders/{order.id}/accept", {}, format="json")

        detail = client.get(f"/api/v1/orders/{order.id}").data
        assert [event["to_status"] for event in detail["events"]] == [
            OrderStatus.PLACED,
            OrderStatus.ACCEPTED,
        ]


class TestAddresses:
    def test_adding_and_listing(self, client):
        player = UserFactory()
        client.force_authenticate(player)

        created = client.post(
            "/api/v1/me/addresses",
            {"label": "Home", "line": "Road 27", "area": "Dhanmondi", "is_default": True},
            format="json",
        )
        assert created.status_code == 201
        assert len(client.get("/api/v1/me/addresses").data) == 1

    def test_only_one_default(self, client):
        player = UserFactory()
        client.force_authenticate(player)
        for label in ("Home", "Office"):
            client.post(
                "/api/v1/me/addresses",
                {"label": label, "line": "Road 27", "area": "Dhanmondi", "is_default": True},
                format="json",
            )

        rows = client.get("/api/v1/me/addresses").data
        assert sum(1 for row in rows if row["is_default"]) == 1
