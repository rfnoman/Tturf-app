"""Sport catalogue business logic (DOMAIN §2).

``SportProposal`` is a state machine, so every transition is one function here that
validates the from-state before writing the new one (CLAUDE.md). Nothing else assigns
``proposal.status``.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.core.utils import now

from .models import Sport, SportProposal

logger = logging.getLogger(__name__)


def unique_sport_slug(name: str) -> str:
    """A slug for ``name`` that no existing sport holds.

    Needed because a proposal's name is free text: an admin approving "Beach Volleyball"
    twice (or approving one whose slug collides with an existing sport) would otherwise
    hit an IntegrityError at the end of a long review.
    """
    base = slugify(name)[:72] or "sport"
    slug = base
    suffix = 2
    while Sport.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@transaction.atomic
def create_sport_proposal(*, user, name: str, description: str = "") -> SportProposal:
    """Propose a sport the catalogue does not have.

    A name matching an active sport is rejected up front; the point of proposals is to
    *avoid* duplicates, and telling the proposer immediately beats an admin merging it
    later.
    """
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": "A sport name is required."})

    existing = (
        Sport.objects.filter(slug=slugify(name)).first()
        or Sport.objects.filter(name__iexact=name).first()
    )
    if existing is not None:
        raise ValidationError({"name": f"“{existing.name}” is already in the catalogue."})

    duplicate = SportProposal.objects.filter(
        proposed_by=user, name__iexact=name, status=SportProposal.Status.PENDING
    ).first()
    if duplicate is not None:
        raise ValidationError({"name": "You already have a pending proposal with this name."})

    proposal = SportProposal.objects.create(
        proposed_by=user, name=name, description=(description or "").strip()
    )
    # "name" is the LogRecord's own logger name; overwriting it raises.
    logger.info("Sport proposed", extra={"proposal": str(proposal.id), "sport_name": name})
    return proposal


def _require_pending(proposal: SportProposal) -> None:
    if proposal.status != SportProposal.Status.PENDING:
        raise ValidationError(
            {"status": f"This proposal is already {proposal.get_status_display().lower()}."}
        )


@transaction.atomic
def approve_sport_proposal(
    *,
    proposal: SportProposal,
    reviewer,
    name: str | None = None,
    met_value=None,
    icon: str = "",
    note: str = "",
) -> Sport:
    """``pending -> approved``: create the sport the proposal asked for.

    The admin may correct the name on the way through ("futsal" -> "Futsal"), which is
    why the name is a parameter rather than read straight off the proposal.
    """
    _require_pending(proposal)

    sport_name = (name or proposal.name).strip()
    if Sport.objects.filter(name__iexact=sport_name).exists():
        raise ValidationError(
            {"name": f"A sport named “{sport_name}” exists; merge the proposal instead."}
        )

    fields = {
        "name": sport_name,
        "slug": unique_sport_slug(sport_name),
        "description": proposal.description,
        "icon": icon,
        # A brand-new sport has no formats, skills or stats yet; an admin adds them in
        # the Django admin, and the sport stays inactive until they do.
        "is_active": False,
    }
    if met_value is not None:
        fields["met_value"] = met_value
    sport = Sport.objects.create(**fields)

    proposal.status = SportProposal.Status.APPROVED
    proposal.merged_into = sport
    proposal.review_note = note
    proposal.reviewed_by = reviewer
    proposal.reviewed_at = now()
    proposal.save(
        update_fields=[
            "status",
            "merged_into",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    logger.info(
        "Sport proposal approved",
        extra={"proposal": str(proposal.id), "sport": sport.slug},
    )
    return sport


@transaction.atomic
def merge_sport_proposal(
    *, proposal: SportProposal, reviewer, sport: Sport, note: str = ""
) -> SportProposal:
    """``pending -> merged``: the proposal is a name for a sport we already have."""
    _require_pending(proposal)

    proposal.status = SportProposal.Status.MERGED
    proposal.merged_into = sport
    proposal.review_note = note
    proposal.reviewed_by = reviewer
    proposal.reviewed_at = now()
    proposal.save(
        update_fields=[
            "status",
            "merged_into",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    logger.info(
        "Sport proposal merged",
        extra={"proposal": str(proposal.id), "sport": sport.slug},
    )
    return proposal


@transaction.atomic
def reject_sport_proposal(*, proposal: SportProposal, reviewer, note: str = "") -> SportProposal:
    """``pending -> rejected``. A reason is required: the proposer sees it."""
    _require_pending(proposal)

    note = (note or "").strip()
    if not note:
        raise ValidationError({"review_note": "Give the proposer a reason for the rejection."})

    proposal.status = SportProposal.Status.REJECTED
    proposal.review_note = note
    proposal.reviewed_by = reviewer
    proposal.reviewed_at = now()
    proposal.save(
        update_fields=["status", "review_note", "reviewed_by", "reviewed_at", "updated_at"]
    )
    logger.info("Sport proposal rejected", extra={"proposal": str(proposal.id)})
    return proposal
