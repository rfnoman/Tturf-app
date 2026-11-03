"""Tests for the account services (CLAUDE.md: every service function gets tests)."""

from __future__ import annotations

import pytest
import requests

from apps.accounts.clerk import fetch_clerk_user
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


class TestBackfillFromClerkBackendApi:
    """A session token carries no identity claims, so the first request backfills them.

    Without this the account shows as a nameless "Player" everywhere until a webhook
    arrives — which never happens in local development, where Clerk has no public URL.
    """

    @pytest.fixture
    def clerk_payload(self):
        return {
            "id": "user_backfill",
            "first_name": "Rafi",
            "last_name": "Ahmed",
            "image_url": "https://img.clerk.com/rafi",
            "primary_email_address_id": "idn_1",
            "email_addresses": [{"id": "idn_1", "email_address": "rafi@example.com"}],
            "primary_phone_number_id": "idn_2",
            "phone_numbers": [{"id": "idn_2", "phone_number": "+8801711111111"}],
        }

    def test_fills_a_new_account_from_clerk(self, monkeypatch, clerk_payload):
        monkeypatch.setattr(
            "apps.accounts.services.fetch_clerk_user", lambda clerk_id: clerk_payload
        )

        user = get_or_create_user_from_claims({"sub": "user_backfill"})

        assert user.first_name == "Rafi"
        assert user.email == "rafi@example.com"
        assert user.phone == "+8801711111111"
        assert user.image_url == "https://img.clerk.com/rafi"
        assert user.last_synced_at is not None

    def test_costs_at_most_one_request_per_account(self, monkeypatch, clerk_payload):
        calls = []

        def fake(clerk_id):
            calls.append(clerk_id)
            return clerk_payload

        monkeypatch.setattr("apps.accounts.services.fetch_clerk_user", fake)

        get_or_create_user_from_claims({"sub": "user_backfill"})
        get_or_create_user_from_claims({"sub": "user_backfill"})
        get_or_create_user_from_claims({"sub": "user_backfill"})

        assert calls == ["user_backfill"]

    def test_an_unreachable_clerk_does_not_block_sign_in(self, monkeypatch):
        """A Clerk outage must not 500 the auth path or retry on every request."""
        calls = []

        def fake(clerk_id):
            calls.append(clerk_id)
            return None

        monkeypatch.setattr("apps.accounts.services.fetch_clerk_user", fake)

        user = get_or_create_user_from_claims({"sub": "user_offline"})
        assert user.pk is not None
        assert user.last_synced_at is not None

        get_or_create_user_from_claims({"sub": "user_offline"})
        assert len(calls) == 1

    def test_a_webhook_still_corrects_a_failed_backfill(self, monkeypatch, clerk_payload):
        monkeypatch.setattr("apps.accounts.services.fetch_clerk_user", lambda clerk_id: None)
        get_or_create_user_from_claims({"sub": "user_backfill"})

        synced = sync_user_from_clerk(clerk_payload)
        assert synced.email == "rafi@example.com"
        assert User.objects.filter(clerk_id="user_backfill").count() == 1

    def test_an_already_synced_account_is_left_alone(self, monkeypatch, clerk_payload):
        """A webhook-synced account must not be re-read, nor have edits reverted."""
        sync_user_from_clerk(clerk_payload)
        monkeypatch.setattr(
            "apps.accounts.services.fetch_clerk_user",
            lambda clerk_id: pytest.fail("should not call Clerk for a synced account"),
        )

        user = get_or_create_user_from_claims({"sub": "user_backfill"})
        assert user.email == "rafi@example.com"


class TestFetchClerkUser:
    def test_returns_none_without_a_secret_key(self, settings):
        settings.CLERK_SECRET_KEY = ""
        assert fetch_clerk_user("user_x") is None

    def test_returns_none_when_clerk_errors(self, monkeypatch):
        def boom(*args, **kwargs):
            raise requests.ConnectionError("down")

        monkeypatch.setattr("apps.accounts.clerk.requests.get", boom)
        assert fetch_clerk_user("user_x") is None

    def test_returns_none_on_a_non_object_body(self, monkeypatch):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return ["not", "a", "user"]

        monkeypatch.setattr("apps.accounts.clerk.requests.get", lambda *a, **k: Response())
        assert fetch_clerk_user("user_x") is None

    def test_returns_the_user_object(self, monkeypatch):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"id": "user_x", "first_name": "Rafi"}

        monkeypatch.setattr("apps.accounts.clerk.requests.get", lambda *a, **k: Response())
        assert fetch_clerk_user("user_x")["first_name"] == "Rafi"
