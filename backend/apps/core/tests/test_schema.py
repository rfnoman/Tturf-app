"""The OpenAPI schema is the frontend's type source, so its endpoints are load-bearing.

It is also a complete map of every endpoint and payload, so since Phase 11 step 4 it is
readable by platform admins only on a deployed instance (`API_DOCS_PUBLIC`). The test
settings use that posture, which is why these sign in.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(UserFactory(is_platform_admin=True))
    return client


def test_schema_is_served(admin_client):
    response = admin_client.get(reverse("v1:schema"))

    assert response.status_code == 200
    assert "/api/v1/me" in response.data["paths"]
    assert "/api/v1/health" in response.data["paths"]


def test_schema_documents_bearer_auth(admin_client):
    response = admin_client.get(reverse("v1:schema"))

    schemes = response.data["components"]["securitySchemes"]
    assert schemes["ClerkSessionToken"]["scheme"] == "bearer"


@pytest.mark.parametrize("name", ["v1:swagger-ui", "v1:redoc"])
def test_api_docs_render(name, admin_client):
    """Guards the namespaced `url_name` the docs views reverse."""
    response = admin_client.get(reverse(name))
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["v1:schema", "v1:swagger-ui", "v1:redoc"])
def test_not_readable_without_an_account(name):
    """The posture a deployed instance runs in."""
    assert APIClient().get(reverse(name)).status_code in {401, 403}
