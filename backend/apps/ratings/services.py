"""Turning locked scorecards into ratings, track record and reputation (DOMAIN §8).

The arithmetic lives in `engine.py` and knows nothing about the database. Everything
here is the plumbing either side of it: gathering what a match says about each player,
writing the result where the profile reads it, and keeping the running totals.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg
from django.utils.timezone import now

from apps.core.utils import plain_decimal
from apps.players.models import (
    PlayerAttribute,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
    RatingSource,
)
from apps.players.services import get_or_create_profile
from apps.scoring.models import MatchTeamPlayer, PeerRating, ScorecardStatus, TeamSide

from .engine import MatchPerformance, RatingOutcome, rate_match
from .models import ConductReport, PlayerGroundStats, PlayerSportStats, RatingChange

logger = logging.getLogger(__name__)

#: How many results the form guide keeps (DOMAIN §3: "form (last 5)").
FORM_LENGTH = 5


# ---------------------------------------------------------------------------
# Reading a locked scorecard
# ---------------------------------------------------------------------------
def _outcome_for(side: str, result: str) -> str:
    if not result:
        return "draw"
    if result == "draw":
        return "draw"
    return "win" if result == side else "loss"


def _peer_averages(match_id) -> dict:
    rows = (
        PeerRating.objects.filter(match=match_id)
        .values("ratee_id")
        .annotate(average=Avg("overall"))
    )
    counts = {}
    for row in PeerRating.objects.filter(match=match_id).values("ratee_id"):
        counts[row["ratee_id"]] = counts.get(row["ratee_id"], 0) + 1
    return {
        row["ratee_id"]: (Decimal(str(row["average"])), counts.get(row["ratee_id"], 0))
        for row in rows
    }


def _team_averages(scorecard, sides: dict) -> dict[str, int | None]:
    """Mean current rating of each side, used to weigh the result.

    Taken once per match and stored with the change, so replaying a player's history
    does not quietly re-grade their old matches against today's ratings.
    """
    averages: dict[str, int | None] = {}
    for side in (TeamSide.A, TeamSide.B):
        user_ids = [user_id for user_id, player_side in sides.items() if player_side == side]
        if not user_ids:
            averages[side] = None
            continue
        value = PlayerSportRating.objects.filter(
            profile__user_id__in=user_ids, sport=scorecard.match.sport_id
        ).aggregate(average=Avg("overall"))["average"]
        averages[side] = round(value) if value is not None else None
    return averages


def match_inputs(scorecard) -> dict:
    """``{user_id: input dict}`` — one match, as the engine will see it.

    Kept as plain JSON-safe values: this is exactly what gets stored on the
    `RatingChange` and replayed later.
    """
    match = scorecard.match
    sides = {
        entry.match_player.player_id: entry.team.side
        for entry in MatchTeamPlayer.objects.filter(team__match=match).select_related(
            "team", "match_player"
        )
    }
    stats: dict = {}
    for row in scorecard.player_stats.select_related("stat_definition"):
        stats.setdefault(row.player_id, {})[row.stat_definition.key] = plain_decimal(row.value)

    peers = _peer_averages(match.id)
    averages = _team_averages(scorecard, sides)

    inputs = {}
    for user_id, side in sides.items():
        peer_average, peer_count = peers.get(user_id, (None, 0))
        player_stats = stats.get(user_id, {})
        inputs[user_id] = {
            "sport_slug": match.sport.slug,
            "side": side,
            "stats": player_stats,
            "result": _outcome_for(side, scorecard.result),
            "minutes": player_stats.get("minutes_played"),
            "team_average": averages.get(side),
            "opponent_average": averages.get(TeamSide.B if side == TeamSide.A else TeamSide.A),
            "is_motm": user_id == scorecard.motm_id,
            "peer_average": str(peer_average) if peer_average is not None else None,
            "peer_count": peer_count,
            "verified": scorecard.verified_by_staff,
        }
    return inputs


def _performance(stored: dict, *, profile, sport) -> MatchPerformance:
    """Rebuild the engine's input from a stored snapshot plus where the player stands."""
    skills = {
        row.sport_skill.key: row.value
        for row in PlayerSkill.objects.filter(
            profile=profile, sport_skill__sport=sport
        ).select_related("sport_skill")
    }
    attributes = {
        row.attribute.key: row.value
        for row in PlayerAttribute.objects.filter(profile=profile).select_related("attribute")
    }
    rating = PlayerSportRating.objects.filter(profile=profile, sport=sport).first()

    return MatchPerformance(
        sport_slug=stored["sport_slug"],
        stats={key: Decimal(value) for key, value in (stored.get("stats") or {}).items()},
        result=stored.get("result", "draw"),
        minutes=Decimal(stored["minutes"]) if stored.get("minutes") else None,
        team_average=stored.get("team_average"),
        opponent_average=stored.get("opponent_average"),
        is_motm=bool(stored.get("is_motm")),
        peer_average=Decimal(stored["peer_average"]) if stored.get("peer_average") else None,
        peer_count=int(stored.get("peer_count") or 0),
        verified=bool(stored.get("verified")),
        current_overall=rating.overall if rating else int(settings.ONBOARDING_DEFAULT_RATING),
        current_skills=skills,
        current_attributes=attributes,
        matches_counted=rating.matches_counted if rating else 0,
    )


# ---------------------------------------------------------------------------
# Applying a match
# ---------------------------------------------------------------------------
def _write_outcome(*, profile, sport, outcome: RatingOutcome) -> None:
    """Store what the engine decided, marking every value it touched as computed."""
    skills = {
        row.sport_skill.key: row
        for row in PlayerSkill.objects.filter(
            profile=profile, sport_skill__sport=sport
        ).select_related("sport_skill")
    }
    for key, value in outcome.skills.items():
        row = skills.get(key)
        if row is None:
            continue
        row.value = value
        row.source = RatingSource.COMPUTED
        row.save(update_fields=["value", "source", "updated_at"])

    attributes = {
        row.attribute.key: row
        for row in PlayerAttribute.objects.filter(profile=profile).select_related("attribute")
    }
    for key, value in outcome.attributes.items():
        row = attributes.get(key)
        if row is None:
            continue
        row.value = value
        row.source = RatingSource.COMPUTED
        row.save(update_fields=["value", "source", "updated_at"])


def _unlock_sport(*, profile, sport) -> None:
    """DOMAIN §3: playing a locked match of a sport verifies it, adding it if need be."""
    player_sport, created = PlayerSport.objects.get_or_create(
        profile=profile, sport=sport, defaults={"is_verified": True}
    )
    if not player_sport.is_verified or player_sport.is_hidden:
        player_sport.is_verified = True
        player_sport.is_hidden = False
        player_sport.save(update_fields=["is_verified", "is_hidden", "updated_at"])
    if created:
        logger.info(
            "Sport unlocked by playing",
            extra={"profile": str(profile.id), "sport": sport.slug},
        )


def _update_counters(*, rating: PlayerSportRating, result: str, is_motm: bool, played_at) -> None:
    rating.matches_counted += 1
    rating.matches_played += 1
    if result == "win":
        rating.wins += 1
    elif result == "loss":
        rating.losses += 1
    else:
        rating.draws += 1
    if is_motm:
        rating.motm_awards += 1
    rating.last_match_at = played_at
    rating.is_provisional = rating.matches_counted < int(settings.RATING_PROVISIONAL_MATCHES)


def push_form(results, outcome: str) -> list[str]:
    """The form guide: most recent first, only the last few (DOMAIN §3)."""
    return [outcome, *list(results or [])][:FORM_LENGTH]


def _add_totals(totals, *, result: str, is_motm: bool, stats: dict) -> None:
    totals.matches += 1
    if result == "win":
        totals.wins += 1
    elif result == "loss":
        totals.losses += 1
    else:
        totals.draws += 1
    if is_motm:
        totals.motm_awards += 1

    running = dict(totals.stat_totals or {})
    for key, value in stats.items():
        # Minutes are a measure of the match, not an achievement to total up.
        if key == "minutes_played":
            continue
        running[key] = plain_decimal(Decimal(running.get(key, "0")) + Decimal(value))
    totals.stat_totals = running


def _update_track_record(*, profile, scorecard, stored: dict) -> None:
    match = scorecard.match
    result = stored["result"]
    is_motm = bool(stored.get("is_motm"))
    stats = stored.get("stats") or {}

    sport_stats, _ = PlayerSportStats.objects.get_or_create(profile=profile, sport=match.sport)
    _add_totals(sport_stats, result=result, is_motm=is_motm, stats=stats)
    # Most recent first, and only the last few: this is a form guide, not an archive.
    sport_stats.recent_results = push_form(sport_stats.recent_results, result)
    sport_stats.save()

    ground_stats, _ = PlayerGroundStats.objects.get_or_create(
        profile=profile,
        turf=match.booking.ground.turf,
        ground=match.booking.ground,
        sport=match.sport,
    )
    _add_totals(ground_stats, result=result, is_motm=is_motm, stats=stats)
    ground_stats.save()


@transaction.atomic
def apply_locked_scorecard(*, scorecard) -> list[RatingChange]:
    """Rate everyone who played, once.

    Idempotent by `(profile, match)`: the hook can fire twice (a retried task, a replayed
    lock) without a player being rated twice for one match.
    """
    if scorecard.status != ScorecardStatus.LOCKED:
        logger.warning(
            "Ignoring a scorecard that is not locked", extra={"scorecard": str(scorecard.id)}
        )
        return []

    match = scorecard.match
    played_at = match.starts_at
    changes: list[RatingChange] = []

    for user_id, stored in match_inputs(scorecard).items():
        entry = match.players.filter(player_id=user_id).select_related("player").first()
        if entry is None:
            continue
        profile = get_or_create_profile(entry.player)
        if RatingChange.objects.filter(profile=profile, match=match).exists():
            continue

        _unlock_sport(profile=profile, sport=match.sport)
        rating, _ = PlayerSportRating.objects.get_or_create(
            profile=profile,
            sport=match.sport,
            defaults={"overall": int(settings.ONBOARDING_DEFAULT_RATING)},
        )

        performance = _performance(stored, profile=profile, sport=match.sport)
        outcome = rate_match(
            performance, provisional_matches=int(settings.RATING_PROVISIONAL_MATCHES)
        )

        before = rating.overall
        _write_outcome(profile=profile, sport=match.sport, outcome=outcome)
        rating.overall = outcome.overall
        _update_counters(
            rating=rating,
            result=stored["result"],
            is_motm=bool(stored.get("is_motm")),
            played_at=played_at,
        )
        rating.save()

        # Attendance, which Phase 04 left for the scorecard to fill in.
        entry.attended = True
        entry.save(update_fields=["attended", "updated_at"])

        _update_track_record(profile=profile, scorecard=scorecard, stored=stored)

        changes.append(
            RatingChange.objects.create(
                profile=profile,
                sport=match.sport,
                match=match,
                inputs=stored,
                before_overall=before,
                after_overall=outcome.overall,
                breakdown=outcome.breakdown,
                weights_version=outcome.weights_version,
                played_at=played_at,
            )
        )

    logger.info(
        "Ratings applied",
        extra={"scorecard": str(scorecard.id), "players": len(changes)},
    )
    return changes


# ---------------------------------------------------------------------------
# Replaying history
# ---------------------------------------------------------------------------
def _baseline(*, profile, sport) -> tuple[int, dict, dict]:
    """Where the player stood before any match: their own self-assessment.

    `PlayerSport.self_assessed` keeps exactly what they claimed at onboarding, which is
    what makes a replay possible at all.
    """
    from apps.players.services import compute_overall

    player_sport = PlayerSport.objects.filter(profile=profile, sport=sport).first()
    claimed = dict((player_sport.self_assessed if player_sport else None) or {})

    skills = {
        row.sport_skill.key: row
        for row in PlayerSkill.objects.filter(
            profile=profile, sport_skill__sport=sport
        ).select_related("sport_skill")
    }
    for key, row in skills.items():
        if key in claimed:
            row.value = clamp_self(claimed[key])
            row.source = RatingSource.SELF
            row.save(update_fields=["value", "source", "updated_at"])

    return compute_overall(profile=profile, sport=sport), claimed, skills


def clamp_self(value) -> int:
    from apps.players.services import clamp_rating

    return clamp_rating(value, source=RatingSource.SELF)


@transaction.atomic
def recompute_all(*, profile, sport) -> PlayerSportRating:
    """Replay every rated match for one (player, sport) from the stored inputs.

    Deterministic by construction: each `RatingChange` carries the match exactly as the
    engine saw it, so a replay re-runs those matches rather than re-grading them against
    whatever everybody's ratings have since become. The result is the same numbers the
    incremental updates produced, which is what makes the engine auditable.
    """
    overall, _claimed, _skills = _baseline(profile=profile, sport=sport)

    rating, _ = PlayerSportRating.objects.get_or_create(
        profile=profile, sport=sport, defaults={"overall": overall}
    )
    rating.overall = overall
    rating.matches_counted = 0
    rating.matches_played = 0
    rating.wins = rating.draws = rating.losses = rating.motm_awards = 0
    rating.last_match_at = None
    rating.is_provisional = True
    rating.save()

    changes = RatingChange.objects.filter(profile=profile, sport=sport).order_by(
        "played_at", "created_at"
    )
    for change in changes:
        performance = _performance(change.inputs, profile=profile, sport=sport)
        outcome = rate_match(
            performance, provisional_matches=int(settings.RATING_PROVISIONAL_MATCHES)
        )

        before = rating.overall
        _write_outcome(profile=profile, sport=sport, outcome=outcome)
        rating.overall = outcome.overall
        _update_counters(
            rating=rating,
            result=change.inputs.get("result", "draw"),
            is_motm=bool(change.inputs.get("is_motm")),
            played_at=change.played_at,
        )
        rating.save()

        change.before_overall = before
        change.after_overall = outcome.overall
        change.breakdown = outcome.breakdown
        change.weights_version = outcome.weights_version
        change.save(
            update_fields=[
                "before_overall",
                "after_overall",
                "breakdown",
                "weights_version",
                "updated_at",
            ]
        )

    return rating


# ---------------------------------------------------------------------------
# Conduct and fair play
# ---------------------------------------------------------------------------
@transaction.atomic
def report_conduct(*, match, reporter, reported, reason: str, details: str = "") -> ConductReport:
    """One roster player reporting another, once per match (DOMAIN §8)."""
    if reporter.id == reported.id:
        raise ValidationError({"reported": "You cannot report yourself."})

    roster = set(match.players.values_list("player_id", flat=True))
    if reporter.id not in roster:
        raise ValidationError({"match": "Only players in the match can report."})
    if reported.id not in roster:
        raise ValidationError({"reported": "That player was not in this match."})
    if reason not in ConductReport.Reason.values:
        raise ValidationError({"reason": "Unknown reason."})
    if ConductReport.objects.filter(match=match, reporter=reporter, reported=reported).exists():
        raise ValidationError({"match": "You have already reported this player for this match."})

    report = ConductReport.objects.create(
        match=match,
        reporter=reporter,
        reported=reported,
        reason=reason,
        details=(details or "").strip(),
    )
    logger.info("Conduct report filed", extra={"report": str(report.id), "reason": reason})
    return report


@transaction.atomic
def review_conduct(
    *, report: ConductReport, reviewer, uphold: bool, note: str = ""
) -> ConductReport:
    """An admin decides. Only an upheld report touches anybody's fair-play score."""
    if not (
        getattr(reviewer, "is_platform_admin", False) or getattr(reviewer, "is_superuser", False)
    ):
        raise ValidationError({"reviewer": "Only a platform admin can review reports."})
    if report.status != ConductReport.Status.OPEN:
        raise ValidationError({"status": "This report has already been reviewed."})

    report.status = ConductReport.Status.UPHELD if uphold else ConductReport.Status.DISMISSED
    report.reviewed_by = reviewer
    report.reviewed_at = now()
    report.review_note = (note or "").strip()
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    return report


def fair_play(*, profile) -> dict:
    """A fair-play score out of 100, and the band it falls in (DOMAIN §8).

    Built from things that actually happened — cards recorded on locked scorecards,
    upheld reports, and the reliability the booking phase already tracks — never from
    open accusations.
    """
    upheld = ConductReport.objects.filter(
        reported=profile.user, status=ConductReport.Status.UPHELD
    ).count()

    cards = {"yellow": Decimal("0"), "red": Decimal("0")}
    for totals in PlayerSportStats.objects.filter(profile=profile):
        for key in cards:
            cards[key] += Decimal((totals.stat_totals or {}).get(key, "0"))

    score = Decimal("100")
    score -= cards["yellow"] * Decimal(str(settings.FAIR_PLAY_YELLOW_PENALTY))
    score -= cards["red"] * Decimal(str(settings.FAIR_PLAY_RED_PENALTY))
    score -= upheld * Decimal(str(settings.FAIR_PLAY_UPHELD_REPORT_PENALTY))
    score = max(Decimal("0"), min(Decimal("100"), score))

    if score >= int(settings.FAIR_PLAY_GOOD_THRESHOLD):
        band = "good"
    elif score >= int(settings.FAIR_PLAY_WARNING_THRESHOLD):
        band = "warning"
    else:
        band = "poor"

    return {
        "score": int(score),
        "band": band,
        "yellow_cards": int(cards["yellow"]),
        "red_cards": int(cards["red"]),
        "upheld_reports": upheld,
    }
