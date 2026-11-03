"""Read-side queries for the catalogue (CLAUDE.md: read-heavy queries live here)."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from .models import (
    Sport,
    SportAttributeWeight,
    SportFormat,
    SportProposal,
    SportSkill,
    StatDefinition,
)


def sport_catalogue(*, include_inactive: bool = False) -> QuerySet[Sport]:
    """Sports with everything the onboarding wizard and scorecards need, in one pass.

    Nested relations are prefetched because the catalogue serializer renders all of
    them; without this a four-sport response is ~40 queries.
    """
    queryset = Sport.objects.all() if include_inactive else Sport.objects.filter(is_active=True)
    return queryset.prefetch_related(
        Prefetch("formats", queryset=SportFormat.objects.filter(is_active=True)),
        Prefetch("skills", queryset=SportSkill.objects.all()),
        Prefetch(
            "attribute_weights",
            queryset=SportAttributeWeight.objects.select_related("attribute"),
        ),
        Prefetch("stat_definitions", queryset=StatDefinition.objects.all()),
    )


def sport_proposals_for(user) -> QuerySet[SportProposal]:
    """A proposer's own proposals."""
    return SportProposal.objects.filter(proposed_by=user).select_related(
        "merged_into", "reviewed_by"
    )


def all_sport_proposals(*, status: str | None = None) -> QuerySet[SportProposal]:
    """Admin review queue."""
    queryset = SportProposal.objects.select_related("proposed_by", "merged_into", "reviewed_by")
    if status:
        queryset = queryset.filter(status=status)
    return queryset
