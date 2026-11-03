import pytest
from rest_framework.test import APIRequestFactory

from apps.accounts.tests.factories import PlatformAdminFactory, UserFactory
from apps.core.permissions import IsPlatformAdmin

pytestmark = pytest.mark.django_db


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


def test_platform_admin_is_allowed():
    assert IsPlatformAdmin().has_permission(_request(PlatformAdminFactory()), None)


def test_superuser_is_allowed():
    user = UserFactory(is_superuser=True)
    assert IsPlatformAdmin().has_permission(_request(user), None)


def test_plain_player_is_denied():
    assert not IsPlatformAdmin().has_permission(_request(UserFactory()), None)


def test_anonymous_is_denied():
    from django.contrib.auth.models import AnonymousUser

    assert not IsPlatformAdmin().has_permission(_request(AnonymousUser()), None)
