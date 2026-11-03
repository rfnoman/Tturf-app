"""Tests for the account services (CLAUDE.md: every service function gets tests)."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.accounts.services import (
    deactivate_user_from_clerk,
    get_or_create_user_from_claims,
    sync_user_from_clerk,
    user_fields_from_clerk_payload,
)

from .factories import PlatformAdminFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_get_or_create_creates_once():
    claims = {"sub": "user_abc"}

    first = get_or_create_user_from_claims(claims)
    second = get_or_create_user_from_claims(claims)

    assert first.pk == second.pk
    assert User.objects.filter(clerk_id="user_abc").count() == 1
    assert not first.has_usable_password()


def test_get_or_create_does_not_overwrite_synced_fields():
    """A session token carries no profile data, so it must not blank what the webhook set."""
    user = UserFactory(clerk_id="user_sync", email="real@example.com", first_name="Rafi")

    returned = get_or_create_user_from_claims({"sub": "user_sync"})

    assert returned.pk == user.pk
    assert returned.email == "real@example.com"
    assert returned.first_name == "Rafi"


def test_primary_email_is_chosen_over_the_first():
    fields = user_fields_from_clerk_payload(
        {
            "email_addresses": [
                {"id": "idn_1", "email_address": "secondary@example.com"},
                {"id": "idn_2", "email_address": "primary@example.com"},
            ],
            "primary_email_address_id": "idn_2",
        }
    )

    assert fields["email"] == "primary@example.com"


def test_falls_back_to_first_address_when_primary_id_is_unknown():
    fields = user_fields_from_clerk_payload(
        {
            "email_addresses": [{"id": "idn_1", "email_address": "only@example.com"}],
            "primary_email_address_id": "idn_missing",
        }
    )

    assert fields["email"] == "only@example.com"


def test_empty_contact_lists_produce_blanks_not_errors():
    fields = user_fields_from_clerk_payload({"id": "user_x"})

    assert fields["email"] == ""
    assert fields["phone"] == ""
    assert fields["first_name"] == ""


def test_null_names_become_blank_strings():
    """Clerk sends JSON null for unset names; the columns are non-nullable."""
    fields = user_fields_from_clerk_payload(
        {"first_name": None, "last_name": None, "image_url": None}
    )

    assert fields["first_name"] == ""
    assert fields["last_name"] == ""
    assert fields["image_url"] == ""


def test_sync_requires_an_id():
    with pytest.raises(ValueError, match="no 'id'"):
        sync_user_from_clerk({"email_addresses": []})


def test_sync_updates_an_existing_user():
    UserFactory(clerk_id="user_known", first_name="Old", email="old@example.com")

    user = sync_user_from_clerk(
        {
            "id": "user_known",
            "first_name": "New",
            "email_addresses": [{"id": "e1", "email_address": "new@example.com"}],
            "primary_email_address_id": "e1",
        }
    )

    assert user.first_name == "New"
    assert user.email == "new@example.com"
    assert User.objects.filter(clerk_id="user_known").count() == 1


def test_sync_preserves_platform_admin_flag():
    """Role flags are ours, not Clerk's; a profile sync must not clear them."""
    PlatformAdminFactory(clerk_id="user_admin")

    user = sync_user_from_clerk({"id": "user_admin", "first_name": "Admin"})

    assert user.is_platform_admin is True


def test_deactivate_requires_an_id():
    with pytest.raises(ValueError, match="no 'id'"):
        deactivate_user_from_clerk({"deleted": True})


def test_deactivate_keeps_the_row():
    UserFactory(clerk_id="user_bye", email="bye@example.com")

    user = deactivate_user_from_clerk({"object": "user", "id": "user_bye", "deleted": True})

    assert user is not None
    assert user.is_active is False
    assert User.objects.filter(clerk_id="user_bye").exists()


def test_deactivate_unknown_user_returns_none():
    assert deactivate_user_from_clerk({"id": "user_nope", "deleted": True}) is None


def test_full_name_and_str():
    user = UserFactory(clerk_id="user_name", first_name="Rafi", last_name="Ahmed")
    assert user.full_name == "Rafi Ahmed"
    assert str(user) == "Rafi Ahmed"

    nameless = UserFactory(clerk_id="user_nameless", first_name="", last_name="")
    assert str(nameless) == nameless.email
