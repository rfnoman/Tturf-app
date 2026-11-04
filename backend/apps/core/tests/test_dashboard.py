"""The platform dashboard and the support lookup (Phase 11 step 6)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    client = APIClient()
    client.force_authenticate(UserFactory(is_platform_admin=True))
    return client


class TestDashboard:
    def test_an_ordinary_player_cannot_read_it(self):
        client = APIClient()
        client.force_authenticate(UserFactory())

        assert client.get("/api/v1/admin/dashboard").status_code == 403

    def test_an_empty_platform_reports_zeroes_rather_than_failing(self, admin):
        """Launch day: no bookings yet, and the no-show rate must not divide by zero."""
        response = admin.get("/api/v1/admin/dashboard")

        assert response.status_code == 200
        assert response.data["bookings"] == 0
        assert response.data["no_show_rate"] == 0.0

    def test_every_day_in_the_window_appears_even_with_no_bookings(self, admin):
        # A chart that silently skips empty days draws a line that looks healthy
        # through an outage.
        response = admin.get("/api/v1/admin/dashboard?days=7")

        assert len(response.data["per_day"]) == 7

    def test_the_window_cannot_be_abused(self, admin):
        assert admin.get("/api/v1/admin/dashboard?days=99999").status_code == 200
        assert admin.get("/api/v1/admin/dashboard?days=-5").status_code == 200
        assert admin.get("/api/v1/admin/dashboard?days=nonsense").status_code == 200


class TestPlayerLookup:
    def test_an_ordinary_player_cannot_use_it(self):
        client = APIClient()
        client.force_authenticate(UserFactory())

        assert client.get("/api/v1/admin/players?q=rafi").status_code == 403

    def test_finds_an_account_by_email(self, admin):
        UserFactory(email="rafi.ahmed@example.com", first_name="Rafi", last_name="Ahmed")

        results = admin.get("/api/v1/admin/players?q=rafi.ahmed").data

        assert len(results) == 1
        assert results[0]["email"] == "rafi.ahmed@example.com"
        assert results[0]["name"] == "Rafi Ahmed"

    def test_finds_an_account_by_name(self, admin):
        UserFactory(email="someone@example.com", first_name="Nabila", last_name="Hossain")

        assert len(admin.get("/api/v1/admin/players?q=nabila").data) == 1

    def test_a_short_query_returns_nothing(self, admin):
        """Two characters would return most of the directory, which is not a lookup."""
        UserFactory(first_name="Rafi")

        assert admin.get("/api/v1/admin/players?q=ra").data == []
        assert admin.get("/api/v1/admin/players?q=").data == []
