"""The abstract bases are load-bearing for every later phase, so assert their contract."""

import uuid

import pytest

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_uuid_primary_key_is_not_sequential():
    first = UserFactory()
    second = UserFactory()

    assert isinstance(first.id, uuid.UUID)
    assert first.id != second.id
    assert first.id.version == 4


def test_timestamps_are_populated_and_updated():
    user = UserFactory()
    created, updated = user.created_at, user.updated_at

    user.first_name = "Changed"
    user.save(update_fields=["first_name", "updated_at"])
    user.refresh_from_db()

    assert user.created_at == created
    assert user.updated_at > updated
