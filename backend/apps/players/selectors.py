"""Read-side queries for player profiles (CLAUDE.md)."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from .models import (
    PlayerAttribute,
    PlayerProfile,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
)

#: How many skills a FIFA-style card shows. DOMAIN §3 asks for "6 key stats".
CARD_SKILL_COUNT = 6


def profile_queryset() -> QuerySet[PlayerProfile]:
    """A profile with everything the card needs, in a fixed number of queries."""
    return PlayerProfile.objects.select_related("user").prefetch_related(
        Prefetch(
            "attributes",
            queryset=PlayerAttribute.objects.select_related("attribute").order_by(
                "attribute__order"
            ),
        ),
        Prefetch(
            "player_sports",
            queryset=PlayerSport.objects.select_related("sport").filter(is_hidden=False),
        ),
        Prefetch("sport_ratings", queryset=PlayerSportRating.objects.select_related("sport")),
        Prefetch(
            "skills",
            queryset=PlayerSkill.objects.select_related(
                "sport_skill", "sport_skill__sport"
            ).order_by("sport_skill__order"),
        ),
    )


def player_sport_cards(profile: PlayerProfile) -> list[dict]:
    """Assemble one card per sport the player has not hidden.

    A card needs three tables (``PlayerSport`` for positions, ``PlayerSportRating`` for
    the overall and record, ``PlayerSkill`` for the bars), so it is built here rather
    than serialized off a single model. Relies on ``profile_queryset`` having
    prefetched all three — iterating the prefetched lists in Python means no extra query
    per sport.
    """
    ratings = {rating.sport_id: rating for rating in profile.sport_ratings.all()}
    skills_by_sport: dict[object, list] = {}
    for skill in profile.skills.all():
        skills_by_sport.setdefault(skill.sport_skill.sport_id, []).append(skill)

    cards = []
    for player_sport in profile.player_sports.all():
        rating = ratings.get(player_sport.sport_id)
        skills = skills_by_sport.get(player_sport.sport_id, [])
        # Keeper-style skills do not count toward the overall, so they sort last and are
        # only shown when the player has nothing better to fill the six slots with.
        skills = sorted(
            skills,
            key=lambda s: (not s.sport_skill.counts_toward_overall, s.sport_skill.order),
        )[:CARD_SKILL_COUNT]
        cards.append(
            {
                "sport": player_sport.sport,
                "positions": player_sport.positions or [],
                "overall": rating.overall if rating else 0,
                "is_provisional": rating.is_provisional if rating else True,
                "is_verified": player_sport.is_verified,
                "matches_played": rating.matches_played if rating else 0,
                "wins": rating.wins if rating else 0,
                "draws": rating.draws if rating else 0,
                "losses": rating.losses if rating else 0,
                "motm_awards": rating.motm_awards if rating else 0,
                "skills": skills,
            }
        )
    return cards


def discoverable_profiles() -> QuerySet[PlayerProfile]:
    """Players who agreed to appear in search (Phase 06 builds the search on top)."""
    return profile_queryset().filter(discoverable=True, onboarding_completed=True)
