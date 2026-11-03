import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_is_public_and_reports_postgis():
    response = APIClient().get(reverse("v1:health"))

    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert response.data["database"] == "ok"
    # Confirms the spatial extension is actually installed, not just the app loaded.
    assert response.data["postgis"].startswith("3.")


def test_health_needs_no_authentication():
    response = APIClient().get(reverse("v1:health"), HTTP_AUTHORIZATION="Bearer nonsense")
    assert response.status_code == 200
