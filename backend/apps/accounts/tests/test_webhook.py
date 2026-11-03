"""Tests for the svix-verified Clerk webhook."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient
from svix.webhooks import Webhook

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

WEBHOOK_URL_NAME = "v1:clerk-webhook"


def user_created_payload(
    *,
    clerk_id: str = "user_2abcDEF",
    email: str = "player@example.com",
    phone: str | None = None,
    event: str = "user.created",
) -> dict:
    """A Clerk user event, shaped like the real thing.

    Note the two email addresses in a deliberately unhelpful order: the primary one is
    second, so code that reaches for ``email_addresses[0]`` picks the wrong address.
    """
    emails = [
        {
            "id": "idn_secondary",
            "email_address": f"secondary+{email}",
            "object": "email_address",
            "verification": {"status": "verified", "strategy": "email_code"},
        },
        {
            "id": "idn_primary",
            "email_address": email,
            "object": "email_address",
            "verification": {"status": "verified", "strategy": "email_code"},
        },
    ]
    phones = []
    if phone:
        phones = [
            {"id": "idn_phone_old", "phone_number": "+8801000000000", "object": "phone_number"},
            {"id": "idn_phone_primary", "phone_number": phone, "object": "phone_number"},
        ]

    return {
        "object": "event",
        "type": event,
        "instance_id": "ins_123",
        "timestamp": int(time.time() * 1000),
        "data": {
            "object": "user",
            "id": clerk_id,
            "email_addresses": emails,
            "primary_email_address_id": "idn_primary",
            "phone_numbers": phones,
            "primary_phone_number_id": "idn_phone_primary" if phone else None,
            "first_name": "Rafi",
            "last_name": "Ahmed",
            "image_url": "https://img.clerk.com/rafi",
            # Legacy Gravatar field; must be ignored in favour of image_url.
            "profile_image_url": "https://www.gravatar.com/avatar?d=mp",
            "created_at": 1654012591514,
            "updated_at": 1654012591835,
        },
    }


def user_deleted_payload(clerk_id: str = "user_2abcDEF") -> dict:
    """``user.deleted`` carries a Deleted Object: only the id is present."""
    return {
        "object": "event",
        "type": "user.deleted",
        "instance_id": "ins_123",
        "timestamp": int(time.time() * 1000),
        "data": {"object": "user", "id": clerk_id, "deleted": True},
    }


def sign(body: bytes, *, msg_id: str, when: datetime, secret: str | None = None) -> dict[str, str]:
    """Produce the svix headers for a body, exactly as Clerk's sender would."""
    wh = Webhook(secret or settings.CLERK_WEBHOOK_SIGNING_SECRET)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(when.timestamp())),
        "svix-signature": wh.sign(msg_id=msg_id, timestamp=when, data=body.decode()),
    }


def post_webhook(payload: dict, *, secret: str | None = None, msg_id: str = "msg_test_1"):
    """Sign a payload the way svix does and POST it."""
    body = json.dumps(payload).encode()
    return APIClient().post(
        reverse(WEBHOOK_URL_NAME),
        data=body,
        content_type="application/json",
        headers=sign(body, msg_id=msg_id, when=datetime.now(UTC), secret=secret),
    )


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_valid_signature_is_accepted():
    response = post_webhook(user_created_payload())

    assert response.status_code == 200
    assert response.data == {"status": "ok", "event": "user.created"}


def test_missing_signature_headers_are_rejected():
    response = APIClient().post(
        reverse(WEBHOOK_URL_NAME),
        data=json.dumps(user_created_payload()),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not User.objects.exists()


def test_signature_from_a_different_secret_is_rejected():
    other_secret = "whsec_b3RoZXJzZWNyZXRvdGhlcnNlY3JldG90aA=="
    response = post_webhook(user_created_payload(), secret=other_secret)

    assert response.status_code == 400
    assert not User.objects.exists()


def test_tampered_body_is_rejected():
    """A body modified after signing must not verify."""
    body = json.dumps(user_created_payload()).encode()
    headers = sign(body, msg_id="msg_1", when=datetime.now(UTC))

    tampered = json.dumps(user_created_payload(clerk_id="user_attacker")).encode()
    response = APIClient().post(
        reverse(WEBHOOK_URL_NAME),
        data=tampered,
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 400
    assert not User.objects.filter(clerk_id="user_attacker").exists()


def test_stale_timestamp_is_rejected():
    """svix enforces a 5-minute window, which is what stops replays."""
    body = json.dumps(user_created_payload()).encode()
    old = datetime.now(UTC) - timedelta(hours=1)

    response = APIClient().post(
        reverse(WEBHOOK_URL_NAME),
        data=body,
        content_type="application/json",
        headers=sign(body, msg_id="msg_old", when=old),
    )

    assert response.status_code == 400
    assert not User.objects.exists()


def test_unconfigured_secret_refuses_to_process(settings):
    settings.CLERK_WEBHOOK_SIGNING_SECRET = ""
    response = APIClient().post(
        reverse(WEBHOOK_URL_NAME),
        data=json.dumps(user_created_payload()),
        content_type="application/json",
        headers={"svix-id": "a", "svix-timestamp": "1", "svix-signature": "v1,x"},
    )

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------


def test_user_created_creates_the_user():
    post_webhook(user_created_payload(clerk_id="user_new", phone="+8801711111111"))

    user = User.objects.get(clerk_id="user_new")
    assert user.email == "player@example.com"  # the primary address, not the first
    assert user.phone == "+8801711111111"
    assert user.first_name == "Rafi"
    assert user.last_name == "Ahmed"
    assert user.image_url == "https://img.clerk.com/rafi"
    assert user.last_synced_at is not None
    assert not user.has_usable_password()


def test_user_created_is_idempotent():
    """Clerk retries deliveries; a replayed create must not duplicate the row."""
    post_webhook(user_created_payload(clerk_id="user_dup"), msg_id="msg_a")
    post_webhook(user_created_payload(clerk_id="user_dup"), msg_id="msg_b")

    assert User.objects.filter(clerk_id="user_dup").count() == 1


def test_user_updated_updates_existing_user():
    User.objects.create_user(clerk_id="user_upd", email="old@example.com", first_name="Old")

    post_webhook(
        user_created_payload(clerk_id="user_upd", email="new@example.com", event="user.updated")
    )

    user = User.objects.get(clerk_id="user_upd")
    assert user.email == "new@example.com"
    assert user.first_name == "Rafi"


def test_user_updated_for_unknown_user_creates_it():
    """Covers a missed `user.created` delivery."""
    response = post_webhook(user_created_payload(clerk_id="user_late", event="user.updated"))

    assert response.status_code == 200
    assert User.objects.filter(clerk_id="user_late").exists()


def test_user_deleted_soft_deactivates():
    User.objects.create_user(clerk_id="user_del", email="bye@example.com")

    response = post_webhook(user_deleted_payload("user_del"))

    assert response.status_code == 200
    user = User.objects.get(clerk_id="user_del")
    # History (bookings, scorecards, ledger) must survive the account going away.
    assert user.is_active is False
    assert user.email == "bye@example.com"


def test_user_deleted_for_unknown_user_is_acknowledged():
    response = post_webhook(user_deleted_payload("user_never_existed"))

    assert response.status_code == 200
    assert response.data["status"] == "ok"


def test_unhandled_event_is_ignored():
    payload = user_created_payload(event="session.created")
    response = post_webhook(payload)

    assert response.status_code == 200
    assert response.data == {"status": "ignored", "event": "session.created"}
    assert not User.objects.exists()


def test_payload_without_id_is_acknowledged_not_retried():
    """Retrying a malformed payload cannot help, so acknowledge and log instead."""
    payload = user_created_payload()
    payload["data"].pop("id")

    response = post_webhook(payload)

    assert response.status_code == 200
    assert response.data["status"] == "ignored"
    assert not User.objects.exists()


def test_webhook_needs_no_authentication():
    """Clerk cannot present a session token; the signature is the credential."""
    response = post_webhook(user_created_payload(clerk_id="user_anon"))

    assert response.status_code == 200
    assert User.objects.filter(clerk_id="user_anon").exists()
