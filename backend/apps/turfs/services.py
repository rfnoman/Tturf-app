"""Turf business logic (DOMAIN §1, §4).

``Turf.status`` and ``TurfMembership.status`` are state machines, so each transition is
one function that validates the from-state before writing the new one, and nothing else
assigns either field (CLAUDE.md).

The rule that matters most here is **price coverage**: a ground cannot be activated while
any open minute has no price. Enforcing it at activation means Phase 03 never has to
decide what to charge for a slot it cannot price.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.core.utils import now

from .availability import uncovered_minutes
from .models import Ground, Turf, TurfMembership

logger = logging.getLogger(__name__)

#: Roles that may change the turf itself, as opposed to operating it day to day.
TURF_EDIT_ROLES = (TurfMembership.Role.OWNER,)
#: Roles that may confirm bookings, take cash and run the counter (Phase 03, 07).
TURF_STAFF_ROLES = (
    TurfMembership.Role.OWNER,
    TurfMembership.Role.MANAGER,
    TurfMembership.Role.CASHIER,
)


def unique_turf_slug(name: str) -> str:
    """A slug no existing turf holds. Two "Champions Turf" venues are entirely normal."""
    base = slugify(name)[:132] or "turf"
    slug = base
    suffix = 2
    while Turf.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def unique_ground_slug(turf: Turf, name: str) -> str:
    base = slugify(name)[:72] or "ground"
    slug = base
    suffix = 2
    while turf.grounds.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


# ---------------------------------------------------------------------------
# Turf lifecycle
# ---------------------------------------------------------------------------
@transaction.atomic
def create_turf(*, owner, **fields) -> Turf:
    """Register a turf in ``draft`` and make the creator its owner.

    The membership is created in the same transaction: a turf with no owner would be
    unreachable through every owner endpoint, since they all authorise by membership.
    """
    name = (fields.pop("name", "") or "").strip()
    if not name:
        raise ValidationError({"name": "A turf name is required."})

    turf = Turf.objects.create(name=name, slug=unique_turf_slug(name), **fields)
    TurfMembership.objects.create(
        turf=turf,
        user=owner,
        role=TurfMembership.Role.OWNER,
        status=TurfMembership.Status.ACTIVE,
        accepted_at=now(),
    )
    logger.info("Turf created", extra={"turf": str(turf.id), "owner": str(owner.id)})
    return turf


def _require_status(turf: Turf, allowed: tuple[str, ...]) -> None:
    if turf.status not in allowed:
        raise ValidationError(
            {"status": f"A {turf.get_status_display().lower()} turf cannot do that."}
        )


@transaction.atomic
def submit_turf_for_review(*, turf: Turf) -> Turf:
    """``draft|rejected -> pending_review``.

    Refused unless the turf is actually reviewable: an admin should never open a queue
    item with no grounds, no hours and no prices, and the owner should hear about it
    before an admin does.
    """
    _require_status(turf, (Turf.Status.DRAFT, Turf.Status.REJECTED))

    problems: dict[str, str] = {}
    if not turf.grounds.exists():
        problems["grounds"] = "Add at least one ground before submitting."
    if not turf.operating_hours.exists():
        problems["operating_hours"] = "Set the opening hours before submitting."
    unpriced = [ground.name for ground in turf.grounds.all() if uncovered_minutes(ground=ground)]
    if unpriced:
        problems["price_rules"] = (
            f"These grounds have open hours with no price: {', '.join(unpriced)}."
        )
    if problems:
        raise ValidationError(problems)

    turf.status = Turf.Status.PENDING_REVIEW
    turf.submitted_at = now()
    turf.rejection_reason = ""
    turf.save(update_fields=["status", "submitted_at", "rejection_reason", "updated_at"])
    logger.info("Turf submitted for review", extra={"turf": str(turf.id)})
    return turf


@transaction.atomic
def approve_turf(*, turf: Turf, reviewer) -> Turf:
    """``pending_review|rejected|suspended -> approved``: the turf becomes public."""
    _require_status(turf, (Turf.Status.PENDING_REVIEW, Turf.Status.REJECTED, Turf.Status.SUSPENDED))

    turf.status = Turf.Status.APPROVED
    turf.rejection_reason = ""
    turf.reviewed_by = reviewer
    turf.reviewed_at = now()
    turf.save(
        update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"]
    )
    logger.info("Turf approved", extra={"turf": str(turf.id)})
    return turf


@transaction.atomic
def reject_turf(*, turf: Turf, reviewer, reason: str) -> Turf:
    """``pending_review -> rejected``. A reason is required: the owner sees it."""
    _require_status(turf, (Turf.Status.PENDING_REVIEW,))

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Tell the owner what to fix."})

    turf.status = Turf.Status.REJECTED
    turf.rejection_reason = reason
    turf.reviewed_by = reviewer
    turf.reviewed_at = now()
    turf.save(
        update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"]
    )
    logger.info("Turf rejected", extra={"turf": str(turf.id)})
    return turf


@transaction.atomic
def suspend_turf(*, turf: Turf, reviewer, reason: str = "") -> Turf:
    """``approved -> suspended``: pulled from public listings without losing history."""
    _require_status(turf, (Turf.Status.APPROVED,))

    turf.status = Turf.Status.SUSPENDED
    turf.rejection_reason = (reason or "").strip()
    turf.reviewed_by = reviewer
    turf.reviewed_at = now()
    turf.save(
        update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"]
    )
    logger.info("Turf suspended", extra={"turf": str(turf.id)})
    return turf


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
@transaction.atomic
def invite_staff(
    *,
    turf: Turf,
    invited_by,
    role: str,
    email: str = "",
    phone: str = "",
    user=None,
) -> TurfMembership:
    """Invite someone to work at this turf (DOMAIN §1).

    The invitee may not have an account yet, so an email or phone is enough; when they
    do, the membership is linked straight away and they see the turf on next sign-in.
    """
    if role not in TurfMembership.Role.values:
        raise ValidationError({"role": f"Unknown role {role!r}."})
    if role == TurfMembership.Role.OWNER:
        raise ValidationError(
            {"role": "Ownership is granted by registering the turf, not by invitation."}
        )

    email = (email or "").strip().lower()
    phone = (phone or "").strip()
    if user is None and not email and not phone:
        raise ValidationError({"email": "An email or phone number is required."})

    if user is None and email:
        from apps.accounts.models import User

        user = User.objects.filter(email__iexact=email).first()

    if user is not None:
        existing = (
            TurfMembership.objects.filter(turf=turf, user=user)
            .exclude(status=TurfMembership.Status.REMOVED)
            .first()
        )
        if existing is not None:
            raise ValidationError(
                {"user": f"{user} already has the {existing.get_role_display().lower()} role here."}
            )

    membership = TurfMembership.objects.create(
        turf=turf,
        user=user,
        invited_email=email,
        invited_phone=phone,
        role=role,
        invited_by=invited_by,
        status=TurfMembership.Status.INVITED,
    )
    logger.info("Staff invited", extra={"turf": str(turf.id), "membership": str(membership.id)})
    return membership


@transaction.atomic
def accept_staff_invite(*, membership: TurfMembership, user) -> TurfMembership:
    """``invited -> active``.

    An invite addressed to an email may only be accepted by that email's owner;
    otherwise a leaked membership id would be enough to join a turf's staff.
    """
    if membership.status != TurfMembership.Status.INVITED:
        raise ValidationError({"status": "This invitation is no longer open."})

    if membership.user_id and membership.user_id != user.id:
        raise ValidationError({"user": "This invitation is for someone else."})
    if not membership.user_id:
        invited = (membership.invited_email or "").lower()
        if invited and (user.email or "").lower() != invited:
            raise ValidationError({"user": "This invitation is for a different email address."})

    membership.user = user
    membership.status = TurfMembership.Status.ACTIVE
    membership.accepted_at = now()
    membership.save(update_fields=["user", "status", "accepted_at", "updated_at"])
    logger.info("Staff invite accepted", extra={"membership": str(membership.id)})
    return membership


@transaction.atomic
def remove_staff(*, membership: TurfMembership) -> TurfMembership:
    """``invited|active -> removed``.

    Kept as a row rather than deleted so Phase 03's "confirmed by" and Phase 07's counter
    sales still resolve to a person after they leave.
    """
    if membership.role == TurfMembership.Role.OWNER:
        raise ValidationError({"role": "The owner cannot be removed from their own turf."})
    if membership.status == TurfMembership.Status.REMOVED:
        return membership

    membership.status = TurfMembership.Status.REMOVED
    membership.save(update_fields=["status", "updated_at"])
    logger.info("Staff removed", extra={"membership": str(membership.id)})
    return membership


# ---------------------------------------------------------------------------
# Grounds and pricing
# ---------------------------------------------------------------------------
@transaction.atomic
def create_ground(*, turf: Turf, name: str, **fields) -> Ground:
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": "A ground name is required."})

    sport_formats = fields.pop("sport_formats", None)
    ground = Ground.objects.create(
        turf=turf, name=name, slug=unique_ground_slug(turf, name), **fields
    )
    if sport_formats:
        ground.sport_formats.set(sport_formats)
    return ground


def validate_price_coverage(*, ground: Ground) -> None:
    """Raise unless every open minute on this ground has a price (DOMAIN §4)."""
    gaps = uncovered_minutes(ground=ground)
    if not gaps:
        return

    from .models import Weekday

    described = ", ".join(
        f"{Weekday(weekday).label} {start:%H:%M}–{end:%H:%M}" for weekday, start, end in gaps[:6]
    )
    more = "" if len(gaps) <= 6 else f" (and {len(gaps) - 6} more)"
    raise ValidationError({"price_rules": f"These open hours have no price: {described}{more}."})


@transaction.atomic
def activate_ground(*, ground: Ground) -> Ground:
    """Make a ground bookable, once it is fully priced and playable."""
    if not ground.turf.operating_hours.exists():
        raise ValidationError({"operating_hours": "Set the turf's opening hours first."})
    if not ground.sport_formats.exists():
        raise ValidationError({"sport_formats": "Choose at least one sport format."})
    validate_price_coverage(ground=ground)

    ground.is_active = True
    ground.save(update_fields=["is_active", "updated_at"])
    logger.info("Ground activated", extra={"ground": str(ground.id)})
    return ground


@transaction.atomic
def deactivate_ground(*, ground: Ground) -> Ground:
    ground.is_active = False
    ground.save(update_fields=["is_active", "updated_at"])
    return ground


# ---------------------------------------------------------------------------
# Membership lookups used by permissions
# ---------------------------------------------------------------------------
def membership_for(*, turf: Turf, user) -> TurfMembership | None:
    """This user's live membership at this turf, or ``None``."""
    if not user or not user.is_authenticated:
        return None
    return TurfMembership.objects.filter(
        turf=turf, user=user, status=TurfMembership.Status.ACTIVE
    ).first()


def has_turf_role(*, turf: Turf, user, roles: tuple[str, ...]) -> bool:
    membership = membership_for(turf=turf, user=user)
    return membership is not None and membership.role in roles
