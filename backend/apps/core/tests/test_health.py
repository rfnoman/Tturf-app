import pytest
from django.conf import settings
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


@pytest.mark.django_db
def test_client_config_is_public_and_mirrors_the_settings():
    """The frontend must not hard-code business rules; this is where it reads them."""
    response = APIClient().get("/api/v1/config")

    assert response.status_code == 200
    assert response.data["self_assessed_rating_cap"] == settings.SELF_ASSESSED_RATING_CAP
    assert response.data["onboarding_default_rating"] == settings.ONBOARDING_DEFAULT_RATING
    assert response.data["rating_provisional_matches"] == settings.RATING_PROVISIONAL_MATCHES
    assert response.data["default_player_weight_kg"] == settings.DEFAULT_PLAYER_WEIGHT_KG
    assert response.data["turf_delivery_cutoff_hours"] == settings.TURF_DELIVERY_CUTOFF_HOURS
    assert response.data["rating_min"] == 1
    assert response.data["rating_max"] == 99
    assert response.data["currency"] == "BDT"
    assert response.data["time_zone"] == "Asia/Dhaka"
