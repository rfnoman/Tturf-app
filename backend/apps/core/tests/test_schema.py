"""The OpenAPI schema is the frontend's type source, so its endpoints are load-bearing."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_schema_is_served():
    response = APIClient().get(reverse("v1:schema"))

    assert response.status_code == 200
    assert "/api/v1/me" in response.data["paths"]
    assert "/api/v1/health" in response.data["paths"]


def test_schema_documents_bearer_auth():
    response = APIClient().get(reverse("v1:schema"))

    schemes = response.data["components"]["securitySchemes"]
    assert schemes["ClerkSessionToken"]["scheme"] == "bearer"


@pytest.mark.parametrize("name", ["v1:swagger-ui", "v1:redoc"])
def test_api_docs_render(name):
    """Guards the namespaced `url_name` the docs views reverse."""
    response = APIClient().get(reverse(name))
    assert response.status_code == 200
