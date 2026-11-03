"""Inventory, counter and rental endpoints, including who may use them."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.inventory.models import OwnerType, Product, ProductCategory
from apps.inventory.services import rent_out
from apps.players.services import get_or_create_profile
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfMembershipFactory

from .factories import reload, rental_product, stocked_turf

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def owner_of(turf):
    return TurfMembershipFactory(
        turf=turf, role=TurfMembership.Role.OWNER, status=TurfMembership.Status.ACTIVE
    ).user


class TestPublicReads:
    def test_a_turfs_products_are_public(self, client):
        turf, _cashier, product, _item = stocked_turf()
        response = client.get(f"/api/v1/turfs/{turf.slug}/products")

        assert response.status_code == 200
        assert [row["name"] for row in response.data] == [product.name]

    def test_an_inactive_product_is_not_listed(self, client):
        turf, _cashier, product, _item = stocked_turf()
        product.is_active = False
        product.save(update_fields=["is_active"])

        assert client.get(f"/api/v1/turfs/{turf.slug}/products").data == []

    def test_the_nutrition_panel_comes_with_the_product(self, client):
        turf, _cashier, product, _item = stocked_turf()
        product.calories = 110
        product.serving_size = "500 ml"
        product.save(update_fields=["calories", "serving_size"])

        row = client.get(f"/api/v1/turfs/{turf.slug}/products").data[0]
        assert row["nutrition"]["calories"] == 110
        assert row["nutrition"]["serving_size"] == "500 ml"

    def test_the_platform_catalogue_is_public(self, client):
        Product.objects.create(
            owner_type=OwnerType.PLATFORM,
            turf=None,
            slug="whey",
            name="Whey protein",
            base_price=Decimal("4200.00"),
            category=ProductCategory.objects.get(slug="supplements"),
        )
        response = client.get("/api/v1/store/products")

        assert response.status_code == 200
        assert [row["name"] for row in response.data] == ["Whey protein"]

    def test_products_filter_by_tag(self, client):
        turf, _cashier, product, _item = stocked_turf()
        product.tags = ["hydration"]
        product.save(update_fields=["tags"])

        assert len(client.get(f"/api/v1/turfs/{turf.slug}/products?tag=hydration").data) == 1
        assert client.get(f"/api/v1/turfs/{turf.slug}/products?tag=protein").data == []


class TestProductManagement:
    def test_an_owner_adds_a_product_and_it_gets_a_stock_row(self, client):
        turf, _cashier, _product, _item = stocked_turf()
        client.force_authenticate(owner_of(turf))

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/products",
            {
                "category": "food",
                "name": "Banana",
                "base_price": "15.00",
                "perishable": True,
                "tags": ["pre_match", "vegan"],
                "calories": 90,
            },
            format="json",
        )

        assert response.status_code == 201
        product = Product.objects.get(id=response.data["id"])
        assert product.turf == turf
        assert product.owner_type == OwnerType.TURF
        # Visible on the stock screen from the moment it exists.
        assert product.stock_items.count() == 1

    def test_rental_gear_needs_a_rental_price(self, client):
        turf, _cashier, _product, _item = stocked_turf()
        client.force_authenticate(owner_of(turf))

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/products",
            {"category": "rental", "name": "Bibs", "base_price": "0.00", "kind": "rental"},
            format="json",
        )
        assert response.status_code == 400
        assert "rental_price_per_match" in response.data

    def test_a_cashier_cannot_add_products(self, client):
        turf, cashier, _product, _item = stocked_turf()
        client.force_authenticate(cashier)

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/products",
            {"category": "food", "name": "Banana", "base_price": "15.00"},
            format="json",
        )
        assert response.status_code == 403

    def test_a_cashier_can_still_read_the_shelf(self, client):
        turf, cashier, _product, _item = stocked_turf()
        client.force_authenticate(cashier)

        assert client.get(f"/api/v1/me/turfs/{turf.slug}/products").status_code == 200

    def test_another_turfs_staff_see_nothing(self, client):
        turf, _cashier, _product, _item = stocked_turf()
        other_turf, other_cashier, _p, _i = stocked_turf()
        client.force_authenticate(other_cashier)

        assert client.get(f"/api/v1/me/turfs/{turf.slug}/products").status_code == 404

    def test_retiring_a_product_deactivates_it(self, client):
        turf, _cashier, product, _item = stocked_turf()
        client.force_authenticate(owner_of(turf))

        response = client.delete(f"/api/v1/me/turfs/{turf.slug}/products/{product.id}")

        assert response.status_code == 204
        product.refresh_from_db()
        assert product.is_active is False


class TestStockApi:
    def test_the_stock_list_shows_what_is_available(self, client):
        turf, cashier, _product, item = stocked_turf(on_hand=10)
        client.force_authenticate(cashier)

        row = client.get(f"/api/v1/me/turfs/{turf.slug}/stock").data[0]
        assert row["on_hand"] == 10
        assert row["available"] == 10
        assert row["is_low"] is False

    def test_receiving_stock_through_the_api(self, client):
        turf, _cashier, _product, item = stocked_turf(on_hand=0)
        client.force_authenticate(owner_of(turf))

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/stock/{item.id}/receive",
            {"quantity": 24, "note": "Friday delivery"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["on_hand"] == 24

    def test_an_adjustment_without_a_reason_is_rejected(self, client):
        turf, _cashier, _product, item = stocked_turf()
        client.force_authenticate(owner_of(turf))

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/stock/{item.id}/adjust",
            {"delta": -1, "reason": ""},
            format="json",
        )
        assert response.status_code == 400

    def test_taking_out_more_than_there_is_conflicts(self, client):
        turf, _cashier, _product, item = stocked_turf(on_hand=1)
        client.force_authenticate(owner_of(turf))

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/stock/{item.id}/adjust",
            {"delta": -5, "reason": "Count"},
            format="json",
        )
        # 409, not 400: the request was fine, the shelf was not.
        assert response.status_code == 409

    def test_the_movement_log_reads_back(self, client):
        turf, cashier, _product, item = stocked_turf(on_hand=5)
        client.force_authenticate(cashier)

        response = client.get(f"/api/v1/me/turfs/{turf.slug}/stock/{item.id}/movements")

        assert response.status_code == 200
        assert response.data[0]["type"] == "purchase"
        assert response.data[0]["qty_delta"] == 5

    def test_a_location_price_override(self, client):
        turf, _cashier, _product, item = stocked_turf(price="25.00")
        client.force_authenticate(owner_of(turf))

        response = client.patch(
            f"/api/v1/me/turfs/{turf.slug}/stock/{item.id}",
            {"price_override": "30.00"},
            format="json",
        )
        assert response.status_code == 200
        assert Decimal(response.data["price"]) == Decimal("30.00")


class TestCounterApi:
    def test_a_cashier_rings_up_a_sale(self, client):
        turf, cashier, product, item = stocked_turf(on_hand=10, price="25.00")
        client.force_authenticate(cashier)

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {
                "lines": [{"product_id": str(product.id), "quantity": 3}],
                "cash_received": "100.00",
            },
            format="json",
        )

        assert response.status_code == 201
        assert Decimal(response.data["total"]) == Decimal("75.00")
        assert Decimal(response.data["change_due"]) == Decimal("25.00")
        assert reload(item).on_hand == 7

    def test_selling_a_product_from_another_turf_is_refused(self, client):
        turf, cashier, _product, _item = stocked_turf()
        _other, _other_cashier, other_product, _other_item = stocked_turf()
        client.force_authenticate(cashier)

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {"lines": [{"product_id": str(other_product.id), "quantity": 1}]},
            format="json",
        )
        assert response.status_code == 400

    def test_overselling_at_the_counter_conflicts(self, client):
        turf, cashier, product, _item = stocked_turf(on_hand=1)
        client.force_authenticate(cashier)

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {"lines": [{"product_id": str(product.id), "quantity": 5}]},
            format="json",
        )
        assert response.status_code == 409

    def test_a_player_cannot_sell_at_a_counter(self, client):
        turf, _cashier, product, _item = stocked_turf()
        client.force_authenticate(UserFactory())

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {"lines": [{"product_id": str(product.id), "quantity": 1}]},
            format="json",
        )
        assert response.status_code == 404

    def test_todays_sales_list(self, client):
        turf, cashier, product, _item = stocked_turf(on_hand=10)
        client.force_authenticate(cashier)
        client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {"lines": [{"product_id": str(product.id), "quantity": 1}]},
            format="json",
        )

        response = client.get(f"/api/v1/me/turfs/{turf.slug}/counter-sales")
        assert len(response.data) == 1
        assert response.data[0]["lines"][0]["quantity"] == 1

    def test_voiding_a_sale(self, client):
        turf, cashier, product, item = stocked_turf(on_hand=10)
        client.force_authenticate(cashier)
        sale_id = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales",
            {"lines": [{"product_id": str(product.id), "quantity": 2}]},
            format="json",
        ).data["id"]

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/counter-sales/{sale_id}/void",
            {"reason": "Rang up twice"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "voided"
        assert reload(item).on_hand == 10


class TestRentalApi:
    def test_handing_gear_over_and_getting_it_back(self, client):
        turf, cashier, _product, _item = stocked_turf()
        bibs, bib_item = rental_product(turf, on_hand=3)
        player = UserFactory()
        profile = get_or_create_profile(player)
        client.force_authenticate(cashier)

        created = client.post(
            f"/api/v1/me/turfs/{turf.slug}/rentals",
            {"product_id": str(bibs.id), "player_id": str(profile.id), "quantity": 1},
            format="json",
        )

        assert created.status_code == 201
        assert created.data["status"] == "out"
        assert reload(bib_item).available == 2

        returned = client.post(
            f"/api/v1/me/turfs/{turf.slug}/rentals/{created.data['id']}/return",
            {},
            format="json",
        )
        assert returned.status_code == 200
        assert returned.data["status"] == "returned"
        assert reload(bib_item).available == 3

    def test_gear_that_is_lost_is_charged(self, client):
        turf, cashier, _product, _item = stocked_turf()
        bibs, _bib_item = rental_product(turf)
        rental = rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier, quantity=1)
        client.force_authenticate(cashier)

        response = client.post(
            f"/api/v1/me/turfs/{turf.slug}/rentals/{rental.id}/lost",
            {"charges": "500.00"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "lost"
        assert Decimal(response.data["charges"]) == Decimal("500.00")

    def test_the_board_shows_what_is_still_out(self, client):
        turf, cashier, _product, _item = stocked_turf()
        bibs, _bib_item = rental_product(turf)
        rent_out(turf=turf, product=bibs, player=UserFactory(), actor=cashier)
        client.force_authenticate(cashier)

        response = client.get(f"/api/v1/me/turfs/{turf.slug}/rentals")
        assert len(response.data) == 1
        assert response.data[0]["status"] == "out"


class TestWarehouse:
    def test_only_a_platform_admin_sees_the_warehouse(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/admin/warehouse/stock").status_code == 403

    def test_an_admin_adds_a_platform_product_and_receives_stock(self, client):
        client.force_authenticate(UserFactory(is_platform_admin=True))

        created = client.post(
            "/api/v1/admin/warehouse/products",
            {"category": "supplements", "name": "Whey protein 1kg", "base_price": "4200.00"},
            format="json",
        )
        assert created.status_code == 201

        item_id = client.get("/api/v1/admin/warehouse/stock").data[0]["id"]
        received = client.post(
            f"/api/v1/admin/warehouse/stock/{item_id}/receive",
            {"quantity": 30},
            format="json",
        )

        assert received.status_code == 200
        assert received.data["on_hand"] == 30

    def test_a_platform_product_is_not_on_a_turf_shelf(self, client):
        turf, _cashier, _product, _item = stocked_turf()
        admin = UserFactory(is_platform_admin=True)
        client.force_authenticate(admin)
        client.post(
            "/api/v1/admin/warehouse/products",
            {"category": "gear", "name": "Football", "base_price": "1800.00"},
            format="json",
        )

        names = [row["name"] for row in client.get(f"/api/v1/turfs/{turf.slug}/products").data]
        assert "Football" not in names


def test_the_seeded_catalogue_is_consistent(django_db_setup):
    """`seed_demo` must never leave a shelf whose ledger disagrees with it."""
    from django.core.management import call_command

    from apps.inventory.models import StockItem
    from apps.inventory.services import ledger_totals

    call_command("seed_demo", verbosity=0)

    for item in StockItem.objects.all():
        on_hand, reserved = ledger_totals(item)
        assert (item.on_hand, item.reserved) == (on_hand, reserved), item
