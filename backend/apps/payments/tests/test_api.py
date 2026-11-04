"""Payment endpoints, including the one a stranger can post to."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import BookingStatus
from apps.payments.models import PaymentKind, PaymentStatus
from apps.payments.providers.base import ValidationResult
from apps.payments.services import settle_payment, start_online_payment
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfMembershipFactory

from .factories import payable_booking

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def owner_of(turf):
    return TurfMembershipFactory(
        turf=turf, role=TurfMembership.Role.OWNER, status=TurfMembership.Status.ACTIVE
    ).user


class TestStartingApi:
    def test_a_player_starts_a_payment_for_their_booking(self, client):
        booking = payable_booking(price="2000.00", advance_percent=25)
        client.force_authenticate(booking.booked_by)

        response = client.post(
            "/api/v1/payments/start",
            {"booking_id": str(booking.id), "method": "sslcommerz", "kind": "advance"},
            format="json",
        )

        assert response.status_code == 201
        assert Decimal(response.data["amount"]) == Decimal("500.00")
        assert response.data["redirect_url"].startswith("https://")

    def test_somebody_elses_booking_is_not_found(self, client):
        booking = payable_booking()
        client.force_authenticate(UserFactory())

        response = client.post(
            "/api/v1/payments/start",
            {"booking_id": str(booking.id), "method": "sslcommerz"},
            format="json",
        )
        assert response.status_code == 404

    def test_naming_both_a_booking_and_an_order_is_refused(self, client):
        booking = payable_booking()
        client.force_authenticate(booking.booked_by)

        response = client.post(
            "/api/v1/payments/start",
            {
                "booking_id": str(booking.id),
                "order_id": str(booking.id),
                "method": "sslcommerz",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_signing_in_is_required(self, client):
        assert client.post("/api/v1/payments/start", {}, format="json").status_code == 401


class TestIpn:
    """The only unauthenticated write in the app."""

    def test_a_valid_ipn_settles_the_payment(self, client):
        booking = payable_booking()
        payment = start_online_payment(
            target=booking, method="sslcommerz", kind=PaymentKind.ADVANCE
        )

        response = client.post(
            "/api/v1/payments/ipn/sslcommerz",
            {"tran_id": payment.provider_txn_id, "val_id": "V1", "status": "VALID"},
            format="json",
        )

        assert response.status_code == 200
        payment.refresh_from_db()
        booking.refresh_from_db()
        assert payment.status == PaymentStatus.PAID
        assert booking.status == BookingStatus.CONFIRMED

    def test_a_forged_ipn_moves_nothing(self, client, fake_gateway):
        """Anyone can post here; the provider is what decides."""
        fake_gateway.answer = ValidationResult(is_paid=False, status="FAILED")
        booking = payable_booking()
        payment = start_online_payment(target=booking, method="sslcommerz")

        client.post(
            "/api/v1/payments/ipn/sslcommerz",
            {"tran_id": payment.provider_txn_id, "val_id": "FORGED", "status": "VALID"},
            format="json",
        )

        booking.refresh_from_db()
        assert booking.status == BookingStatus.RESERVED

    def test_an_ipn_for_nothing_is_answered_politely(self, client):
        """200, so the gateway stops retrying something that can never work."""
        response = client.post(
            "/api/v1/payments/ipn/sslcommerz",
            {"tran_id": "NOT-OURS", "val_id": "V1"},
            format="json",
        )
        assert response.status_code == 200

    def test_a_duplicate_ipn_is_harmless(self, client):
        booking = payable_booking()
        payment = start_online_payment(target=booking, method="sslcommerz")
        body = {"tran_id": payment.provider_txn_id, "val_id": "V1", "status": "VALID"}

        client.post("/api/v1/payments/ipn/sslcommerz", body, format="json")
        before = booking.events.count()
        client.post("/api/v1/payments/ipn/sslcommerz", body, format="json")

        booking.refresh_from_db()
        assert booking.events.count() == before

    def test_the_ipn_needs_no_session(self, client):
        """A gateway has no cookie; an endpoint that demanded one would never work."""
        response = client.post("/api/v1/payments/ipn/sslcommerz", {}, format="json")
        assert response.status_code != 401


class TestPaymentDetail:
    def test_the_result_page_settles_on_arrival(self, client):
        """The player usually gets back before the IPN does."""
        booking = payable_booking()
        payment = start_online_payment(target=booking, method="sslcommerz")
        client.force_authenticate(booking.booked_by)

        response = client.get(f"/api/v1/payments/{payment.id}?val_id=V1")

        assert response.status_code == 200
        assert response.data["status"] == PaymentStatus.PAID

    def test_a_stranger_cannot_read_a_payment(self, client):
        booking = payable_booking()
        payment = start_online_payment(target=booking, method="sslcommerz")
        client.force_authenticate(UserFactory())

        assert client.get(f"/api/v1/payments/{payment.id}").status_code == 403

    def test_my_payments_lists_only_mine(self, client):
        mine = payable_booking()
        theirs = payable_booking()
        start_online_payment(target=mine, method="sslcommerz")
        start_online_payment(target=theirs, method="sslcommerz")
        client.force_authenticate(mine.booked_by)

        rows = client.get("/api/v1/me/payments").data

        assert len(rows) == 1
        assert rows[0]["what_for"].startswith(mine.ground.turf.name)


class TestRefundQuote:
    def test_a_player_can_see_what_they_would_get_back(self, client):
        booking = payable_booking()
        payment = start_online_payment(target=booking, method="sslcommerz", kind=PaymentKind.FULL)
        settle_payment(payment=payment, callback={"val_id": "V1"})
        client.force_authenticate(booking.booked_by)

        response = client.get(f"/api/v1/bookings/{booking.id}/refund-quote")

        assert response.status_code == 200
        assert Decimal(response.data["amount"]) > 0

    def test_a_stranger_cannot(self, client):
        booking = payable_booking()
        client.force_authenticate(UserFactory())

        assert client.get(f"/api/v1/bookings/{booking.id}/refund-quote").status_code == 403


class TestFinance:
    def paid(self, *, price="2000.00"):
        booking = payable_booking(price=price)
        payment = start_online_payment(target=booking, method="sslcommerz", kind=PaymentKind.FULL)
        settle_payment(payment=payment, callback={"val_id": "V1"})
        return booking

    def test_an_owner_sees_their_earnings(self, client):
        booking = self.paid()
        turf = booking.ground.turf
        client.force_authenticate(owner_of(turf))

        response = client.get(f"/api/v1/me/turfs/{turf.slug}/finance")

        assert response.status_code == 200
        assert Decimal(response.data["total"]) == Decimal("1800.00")
        assert len(response.data["entries"]) == 1

    def test_a_cashier_cannot_see_the_money(self, client):
        booking = self.paid()
        turf = booking.ground.turf
        cashier = TurfMembershipFactory(
            turf=turf, role=TurfMembership.Role.CASHIER, status=TurfMembership.Status.ACTIVE
        ).user
        client.force_authenticate(cashier)

        assert client.get(f"/api/v1/me/turfs/{turf.slug}/finance").status_code == 403

    def test_the_statement_downloads_as_csv(self, client):
        booking = self.paid()
        turf = booking.ground.turf
        client.force_authenticate(owner_of(turf))

        response = client.get(f"/api/v1/me/turfs/{turf.slug}/finance.csv")

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert b"Total" in response.content

    def test_the_platform_dashboard_is_admin_only(self, client):
        client.force_authenticate(UserFactory())
        assert client.get("/api/v1/admin/finance").status_code == 403

    def test_an_admin_sees_the_platforms_position(self, client):
        self.paid()
        client.force_authenticate(UserFactory(is_platform_admin=True))

        response = client.get("/api/v1/admin/finance")

        assert Decimal(response.data["platform"]) == Decimal("200.00")
        assert Decimal(response.data["owed_to_turfs"]) == Decimal("1800.00")

    def test_an_admin_drafts_and_sends_a_payout(self, client):
        from apps.core.utils import now

        booking = self.paid()
        turf = booking.ground.turf
        today = now().date().isoformat()
        client.force_authenticate(UserFactory(is_platform_admin=True))

        created = client.post(
            "/api/v1/admin/payouts",
            {"turf": turf.slug, "period_start": today, "period_end": today},
            format="json",
        )
        assert created.status_code == 201
        assert Decimal(created.data["amount"]) == Decimal("1800.00")

        sent = client.post(
            f"/api/v1/admin/payouts/{created.data['id']}/send",
            {"reference": "BANK-9"},
            format="json",
        )
        assert sent.data["status"] == "sent"

        # The owner's balance is now clear.
        client.force_authenticate(owner_of(turf))
        finance = client.get(f"/api/v1/me/turfs/{turf.slug}/finance")
        assert Decimal(finance.data["total"]) == Decimal("0.00")

    def test_an_admin_can_refund_a_booking(self, client):
        booking = self.paid()
        client.force_authenticate(UserFactory(is_platform_admin=True))

        response = client.post(f"/api/v1/admin/bookings/{booking.id}/refund", {}, format="json")

        assert response.status_code == 200
        assert Decimal(response.data[0]["amount"]) == Decimal("2000.00")
