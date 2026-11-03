"""Player profile business logic (DOMAIN §3).

The onboarding flow is the only writer of a player's first ratings, and it must respect
one hard rule: **self-assessed values are capped** at ``SELF_ASSESSED_RATING_CAP`` so an
unverified player cannot claim 99. The cap is applied here, in the service, rather than
in the serializer — a seed command or a Celery task gets the same guarantee.

``compute_overall`` is deliberately simple in this phase. Phase 06 replaces it with the
versioned engine in ``apps/ratings/engine.py``; what matters now is that the number is
deterministic and that nothing outside this module writes ``PlayerSportRating.overall``.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.utils import now
from apps.sports.models import Attribute, Sport, SportSkill

from .models import (
    RATING_MAX,
    RATING_MIN,
    PlayerAttribute,
    PlayerProfile,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
    RatingSource,
)

logger = logging.getLogger(__name__)

#: How much skills vs. shared attributes contribute to the provisional overall.
#: Configurable per CLAUDE.md; Phase 06's engine takes over from here.
SKILL_SHARE = Decimal(str(settings.OVERALL_SKILL_SHARE))
ATTRIBUTE_SHARE = Decimal(str(settings.OVERALL_ATTRIBUTE_SHARE))


def clamp_rating(value, *, source: str = RatingSource.SELF) -> int:
    """Force a rating into the legal range, applying the self-assessment cap.

    Values arriving from onboarding are capped; computed values are not, so a player who
    earns 90 through matches keeps it.
    """
    try:
        number = round(float(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"value": f"“{value}” is not a rating."}) from exc

    ceiling = RATING_MAX
    if source == RatingSource.SELF:
        ceiling = min(ceiling, int(settings.SELF_ASSESSED_RATING_CAP))
    return max(RATING_MIN, min(ceiling, number))


def get_or_create_profile(user) -> PlayerProfile:
    """The player's profile, created on first access.

    Every signed-in user is a player (DOMAIN §1), so there is no case where a missing
    profile should be an error.
    """
    profile, created = PlayerProfile.objects.get_or_create(
        user=user, defaults={"display_name": user.full_name}
    )
    if created:
        logger.info("Created player profile", extra={"user": str(user.id)})
    return profile


@transaction.atomic
def set_player_attributes(*, profile: PlayerProfile, values: dict, source: str = RatingSource.SELF):
    """Upsert the shared attributes from ``{attribute_key: value}``.

    Unknown keys are an error rather than silently dropped: a typo in the wizard would
    otherwise leave a player with three attributes and no sign of why.
    """
    attributes = {a.key: a for a in Attribute.objects.all()}
    unknown = set(values) - set(attributes)
    if unknown:
        raise ValidationError({"attributes": f"Unknown attributes: {', '.join(sorted(unknown))}."})

    rows = []
    for key, raw in values.items():
        row, _ = PlayerAttribute.objects.update_or_create(
            profile=profile,
            attribute=attributes[key],
            defaults={"value": clamp_rating(raw, source=source), "source": source},
        )
        rows.append(row)
    return rows


@transaction.atomic
def set_player_skills(
    *, profile: PlayerProfile, sport: Sport, values: dict, source: str = RatingSource.SELF
):
    """Upsert this player's skill values for one sport from ``{skill_key: value}``."""
    skills = {s.key: s for s in SportSkill.objects.filter(sport=sport)}
    unknown = set(values) - set(skills)
    if unknown:
        raise ValidationError(
            {"skills": f"{sport.name} has no skills named: {', '.join(sorted(unknown))}."}
        )

    rows = []
    for key, raw in values.items():
        row, _ = PlayerSkill.objects.update_or_create(
            profile=profile,
            sport_skill=skills[key],
            defaults={"value": clamp_rating(raw, source=source), "source": source},
        )
        rows.append(row)
    return rows


def compute_overall(*, profile: PlayerProfile, sport: Sport) -> int:
    """The provisional overall for one (player, sport).

    Weighted mean of the sport's skills (those that ``counts_toward_overall``) blended
    with the player's shared attributes weighted by this sport's ``SportAttributeWeight``
    rows. Either half may be missing — a player who skipped the sliders still gets a
    number rather than an exception — in which case the other half carries the whole
    weight. With nothing at all to go on, the floor is the self-assessment cap's
    midpoint, which keeps a new player visibly "unrated" rather than a 1.
    """
    skill_values = {
        row.sport_skill.key: (row.value, row.sport_skill.weight)
        for row in PlayerSkill.objects.filter(
            profile=profile, sport_skill__sport=sport, sport_skill__counts_toward_overall=True
        ).select_related("sport_skill")
    }
    attribute_weights = {
        row.attribute.key: row.weight for row in sport.attribute_weights.select_related("attribute")
    }
    attribute_values = {
        row.attribute.key: row.value
        for row in PlayerAttribute.objects.filter(profile=profile).select_related("attribute")
    }

    def weighted_mean(pairs: list[tuple[int, Decimal]]) -> Decimal | None:
        total_weight = sum((weight for _, weight in pairs), Decimal(0))
        if total_weight <= 0:
            return None
        return sum((Decimal(value) * weight for value, weight in pairs), Decimal(0)) / total_weight

    skill_mean = weighted_mean([(value, weight) for value, weight in skill_values.values()])
    attribute_mean = weighted_mean(
        [(value, attribute_weights.get(key, Decimal(1))) for key, value in attribute_values.items()]
    )

    if skill_mean is None and attribute_mean is None:
        return int(settings.SELF_ASSESSED_RATING_CAP) // 2
    if skill_mean is None:
        blended = attribute_mean
    elif attribute_mean is None:
        blended = skill_mean
    else:
        blended = skill_mean * SKILL_SHARE + attribute_mean * ATTRIBUTE_SHARE

    return max(RATING_MIN, min(RATING_MAX, int(blended.to_integral_value())))


@transaction.atomic
def refresh_sport_rating(*, profile: PlayerProfile, sport: Sport) -> PlayerSportRating:
    """Recompute and store the overall for one (player, sport).

    The single writer of ``PlayerSportRating.overall``: ``provisional`` is derived from
    ``matches_counted`` here so no caller has to remember the rule.
    """
    overall = compute_overall(profile=profile, sport=sport)
    rating, _ = PlayerSportRating.objects.get_or_create(
        profile=profile, sport=sport, defaults={"overall": overall}
    )
    rating.overall = overall
    rating.is_provisional = rating.matches_counted < int(settings.RATING_PROVISIONAL_MATCHES)
    rating.save(update_fields=["overall", "is_provisional", "updated_at"])
    return rating


@transaction.atomic
def add_player_sport(
    *,
    profile: PlayerProfile,
    sport: Sport,
    positions: list[str] | None = None,
    skills: dict | None = None,
) -> PlayerSport:
    """Add (or un-hide) a sport on this player's profile and rate them in it.

    Re-adding a sport the player removed restores the existing row, so verification and
    match history survive.
    """
    if not sport.is_active:
        raise ValidationError({"sport": f"{sport.name} is not available yet."})

    allowed = set(sport.positions or [])
    chosen = [p for p in (positions or []) if not allowed or p in allowed]
    invalid = set(positions or []) - set(chosen)
    if invalid:
        raise ValidationError(
            {"positions": f"{sport.name} has no position(s): {', '.join(sorted(invalid))}."}
        )

    player_sport, created = PlayerSport.objects.get_or_create(
        profile=profile, sport=sport, defaults={"positions": chosen}
    )
    if not created:
        player_sport.is_hidden = False
        if chosen:
            player_sport.positions = chosen
    if skills:
        player_sport.self_assessed = {**(player_sport.self_assessed or {}), **skills}
    player_sport.save()

    if skills:
        set_player_skills(profile=profile, sport=sport, values=skills)
    refresh_sport_rating(profile=profile, sport=sport)

    logger.info(
        "Player sport added",
        # Note: "created" is a reserved LogRecord attribute, hence is_new.
        extra={"profile": str(profile.id), "sport": sport.slug, "is_new": created},
    )
    return player_sport


@transaction.atomic
def remove_player_sport(*, profile: PlayerProfile, sport: Sport) -> PlayerSport | None:
    """Remove a sport from the profile.

    A sport the player never played is deleted outright; one they *did* play is only
    hidden, because deleting it would orphan scorecard history (phase 01 rules).
    """
    player_sport = PlayerSport.objects.filter(profile=profile, sport=sport).first()
    if player_sport is None:
        return None

    rating = PlayerSportRating.objects.filter(profile=profile, sport=sport).first()
    has_history = player_sport.is_verified or bool(rating and rating.matches_played)
    if has_history:
        player_sport.is_hidden = True
        player_sport.save(update_fields=["is_hidden", "updated_at"])
        return player_sport

    PlayerSkill.objects.filter(profile=profile, sport_skill__sport=sport).delete()
    if rating is not None:
        rating.delete()
    player_sport.delete()
    return None


@transaction.atomic
def complete_onboarding(*, user, data: dict) -> PlayerProfile:
    """Run a new player through onboarding in one transaction (phase 01 step 3).

    ``data`` is the already-validated wizard payload:

        {
          "display_name": "...", "area": "...", "date_of_birth": "...",
          "gender": "...", "height_cm": 175, "weight_kg": "72.5",
          "preferred_side": "right", "bio": "...",
          "attributes": {"stamina": 60, ...},
          "sports": [{"sport": "football", "positions": ["MID"], "skills": {...}}]
        }

    At least one sport is required — the profile card, match board and discovery all key
    off ``PlayerSport``, so finishing with none would leave the player stranded.
    """
    profile = get_or_create_profile(user)

    sports_payload = data.get("sports") or []
    if not sports_payload:
        raise ValidationError({"sports": "Choose at least one sport."})

    slugs = [entry["sport"] for entry in sports_payload]
    sports = {s.slug: s for s in Sport.objects.filter(slug__in=slugs, is_active=True)}
    missing = set(slugs) - set(sports)
    if missing:
        raise ValidationError({"sports": f"Unknown sport(s): {', '.join(sorted(missing))}."})

    profile_fields = (
        "display_name",
        "date_of_birth",
        "gender",
        "height_cm",
        "weight_kg",
        "area",
        "preferred_side",
        "bio",
        "discoverable",
    )
    for field in profile_fields:
        if field in data and data[field] is not None:
            setattr(profile, field, data[field])
    if not profile.display_name:
        profile.display_name = user.full_name

    if data.get("attributes"):
        set_player_attributes(profile=profile, values=data["attributes"])

    for entry in sports_payload:
        add_player_sport(
            profile=profile,
            sport=sports[entry["sport"]],
            positions=entry.get("positions") or [],
            skills=entry.get("skills") or {},
        )

    profile.onboarding_completed = True
    profile.onboarding_completed_at = now()
    profile.save()

    logger.info(
        "Onboarding completed",
        extra={"profile": str(profile.id), "sports": ",".join(sorted(sports))},
    )
    return profile


@transaction.atomic
def update_profile(*, profile: PlayerProfile, data: dict) -> PlayerProfile:
    """Patch editable profile fields, then refresh any ratings the change affects.

    ``attributes`` is accepted here too, because the settings page lets a player redo
    their self-assessment; every sport's overall is recomputed as a result.
    """
    attributes = data.pop("attributes", None)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()

    if attributes:
        set_player_attributes(profile=profile, values=attributes)
        for player_sport in PlayerSport.objects.filter(profile=profile).select_related("sport"):
            refresh_sport_rating(profile=profile, sport=player_sport.sport)

    return profile
