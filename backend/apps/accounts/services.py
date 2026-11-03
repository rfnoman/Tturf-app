"""Account business logic. Views and serializers stay thin (CLAUDE.md)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from .clerk import fetch_clerk_user
from .models import User

logger = logging.getLogger(__name__)


def get_or_create_user_from_claims(claims: dict[str, Any]) -> User:
    """Return the ``User`` for a verified session token, creating it if needed.

    The webhook is the primary sync path, but it can be late, unconfigured, or have
    failed. Creating on first authenticated call means a signed-in user is never left
    without a row.

    A session token carries **no identity claims** (only ``sub``, ``sid``, ``iss`` and
    friends), so a row created here starts with no name or email. Rather than leave the
    account showing as "Player" everywhere until a webhook arrives — which never happens
    in local development, where Clerk has no public URL to call — the profile is
    backfilled once from Clerk's Backend API. Only for a row that has never been synced,
    so this costs at most one request per account, and never on the hot path afterwards.
    """
    clerk_id = claims["sub"]
    user, created = User.objects.get_or_create(clerk_id=clerk_id)
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("Created user from session token", extra={"clerk_id": clerk_id})

    if user.last_synced_at is None:
        backfill_user_from_clerk_api(user)

    return user


def backfill_user_from_clerk_api(user: User) -> User:
    """Fill a never-synced account's name, email and avatar from Clerk.

    ``last_synced_at`` is stamped even when the read fails, so an unreachable Clerk API
    costs one attempt rather than one per request. A later webhook still corrects
    everything.
    """
    payload = fetch_clerk_user(user.clerk_id)
    fields = user_fields_from_clerk_payload(payload) if payload else {}
    fields["last_synced_at"] = timezone.now()

    for field, value in fields.items():
        setattr(user, field, value)
    user.save(update_fields=[*fields, "updated_at"])

    logger.info(
        "Backfilled user from Clerk's Backend API",
        extra={"clerk_id": user.clerk_id, "found": bool(payload)},
    )
    return user


def _primary_contact(items: list[dict[str, Any]], primary_id: str | None, key: str) -> str:
    """Pick the primary email/phone out of a Clerk user payload.

    Clerk does not order these lists, so the primary one must be resolved by matching
    ``primary_*_id`` against each entry's ``id``; ``[0]`` is a real source of bugs.
    """
    if not items:
        return ""
    if primary_id:
        for item in items:
            if item.get("id") == primary_id:
                return item.get(key) or ""
    return items[0].get(key) or ""


def user_fields_from_clerk_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Map a Clerk user object onto our ``User`` fields."""
    return {
        "email": _primary_contact(
            data.get("email_addresses") or [],
            data.get("primary_email_address_id"),
            "email_address",
        ),
        "phone": _primary_contact(
            data.get("phone_numbers") or [],
            data.get("primary_phone_number_id"),
            "phone_number",
        ),
        "first_name": data.get("first_name") or "",
        "last_name": data.get("last_name") or "",
        # `image_url` is current; `profile_image_url` is the legacy Gravatar field.
        "image_url": data.get("image_url") or "",
        "last_synced_at": timezone.now(),
    }


@transaction.atomic
def sync_user_from_clerk(data: dict[str, Any]) -> User:
    """Handle ``user.created`` / ``user.updated``: upsert by ``clerk_id``."""
    clerk_id = data.get("id")
    if not clerk_id:
        raise ValueError("Clerk user payload has no 'id'.")

    fields = user_fields_from_clerk_payload(data)
    user, created = User.objects.update_or_create(clerk_id=clerk_id, defaults=fields)
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])

    logger.info(
        "Synced user from Clerk webhook",
        # "created" is a reserved LogRecord attribute and would raise on INFO.
        extra={"clerk_id": clerk_id, "is_new": created},
    )
    return user


@transaction.atomic
def deactivate_user_from_clerk(data: dict[str, Any]) -> User | None:
    """Handle ``user.deleted``.

    The payload is a Deleted Object — ``{"object": "user", "id": ..., "deleted": true}``
    — so only the id is available. The account is soft-deactivated to keep bookings,
    scorecards and ledger history intact.
    """
    clerk_id = data.get("id")
    if not clerk_id:
        raise ValueError("Clerk delete payload has no 'id'.")

    user = User.objects.filter(clerk_id=clerk_id).first()
    if user is None:
        logger.warning("Delete webhook for unknown user", extra={"clerk_id": clerk_id})
        return None

    user.is_active = False
    user.last_synced_at = timezone.now()
    user.save(update_fields=["is_active", "last_synced_at", "updated_at"])
    logger.info("Deactivated user from Clerk webhook", extra={"clerk_id": clerk_id})
    return user
