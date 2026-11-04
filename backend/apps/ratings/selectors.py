"""Read-side queries: player search, leaderboards and the track record (CLAUDE.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Case, F, FloatField, Q, QuerySet, Value, When
from django.db.models.functions import Coalesce
from django.utils.timezone import now

from apps.players.models import PlayerProfile
from apps.players.selectors import profile_queryset
from apps.sports.models import Sport

from .models import Availability, ConductReport, LeaderboardEntry, PlayerGroundStats


def search_players(
    *,
    viewer=None,
    sport: str | None = None,
    position: str | None = None,
    rating_min: int | None = None,
    rating_max: int | None = None,
    area: str | None = None,
    reliability_min: int | None = None,
    played_at_turf: str | None = None,
    available_from=None,
    available_until=None,
    query: str | None = None,
) -> QuerySet[PlayerProfile]:
    """Find players, respecting `discoverable` (DOMAIN §3).

    `discoverable` gates *search* only — a direct profile link always resolves, which is
    the rule Phase 01 established and this must not quietly tighten.

    Ranking is by fit rather than rating alone: somebody in the same area who turns up
    reliably is a better suggestion than a stranger across the city with a higher number.
    """
    profiles = profile_queryset().filter(discoverable=True)
    if viewer is not None:
        profiles = profiles.exclude(user=viewer)

    if sport:
        profiles = profiles.filter(player_sports__sport__slug=sport, player_sports__is_hidden=False)
    if position and sport:
        profiles = profiles.filter(
            player_sports__sport__slug=sport, player_sports__positions__contains=[position]
        )
    if rating_min is not None or rating_max is not None:
        rating_filter = Q()
        if sport:
            rating_filter &= Q(sport_ratings__sport__slug=sport)
        if rating_min is not None:
            rating_filter &= Q(sport_ratings__overall__gte=rating_min)
        if rating_max is not None:
            rating_filter &= Q(sport_ratings__overall__lte=rating_max)
        profiles = profiles.filter(rating_filter)
    if area:
        profiles = profiles.filter(area__icontains=area)
    if reliability_min is not None:
        profiles = profiles.filter(reliability_score__gte=reliability_min)
    if played_at_turf:
        profiles = profiles.filter(ground_stats__turf__slug=played_at_turf)
    if query:
        profiles = profiles.filter(
            Q(display_name__icontains=query) | Q(user__first_name__icontains=query)
        )

    if available_from or available_until:
        window = Q()
        if available_from:
            window &= Q(availability__ends_at__gt=available_from)
        if available_until:
            window &= Q(availability__starts_at__lt=available_until)
        if sport:
            window &= Q(availability__sport__slug=sport) | Q(availability__sport__isnull=True)
        profiles = profiles.filter(window)

    # Relevance: a shared area, then reliability, then the rating in the sport asked for.
    same_area = Value(0.0, output_field=FloatField())
    if area:
        same_area = Case(
            When(area__iexact=area, then=Value(20.0)),
            default=Value(0.0),
            output_field=FloatField(),
        )

    profiles = profiles.annotate(
        relevance=same_area
        + Coalesce(F("reliability_score"), Value(0)) * Value(0.2, output_field=FloatField())
    ).order_by("-relevance", "-reliability_score", "display_name")

    return profiles.distinct()


def availability_for(*, profile: PlayerProfile, upcoming_only: bool = True):
    windows = Availability.objects.filter(profile=profile).select_related("sport")
    if upcoming_only:
        windows = windows.filter(ends_at__gte=now())
    return windows


def sport_totals(*, profile: PlayerProfile, sport: Sport | None = None) -> dict:
    """Career totals and the form guide, per sport (DOMAIN §3)."""
    from .models import PlayerSportStats

    rows = PlayerSportStats.objects.filter(profile=profile).select_related("sport")
    if sport is not None:
        rows = rows.filter(sport=sport)

    return {
        row.sport.slug: {
            "sport": row.sport.display_name,
            "matches": row.matches,
            "wins": row.wins,
            "draws": row.draws,
            "losses": row.losses,
            "motm_awards": row.motm_awards,
            "stat_totals": row.stat_totals,
            "form": row.recent_results,
        }
        for row in rows
    }


def track_record(*, profile: PlayerProfile, sport: Sport | None = None) -> list[dict]:
    """Per-ground highlights — "3× MOTM at Mirpur Turf Club" (DOMAIN §8)."""
    rows = PlayerGroundStats.objects.filter(profile=profile).select_related(
        "turf", "ground", "sport"
    )
    if sport is not None:
        rows = rows.filter(sport=sport)

    return [
        {
            "turf_name": row.turf.name,
            "turf_slug": row.turf.slug,
            "ground_name": row.ground.name,
            "sport": row.sport.display_name,
            "matches": row.matches,
            "wins": row.wins,
            "draws": row.draws,
            "losses": row.losses,
            "motm_awards": row.motm_awards,
            "stat_totals": row.stat_totals,
        }
        for row in rows.order_by("-matches")
    ]


def open_conduct_reports() -> QuerySet[ConductReport]:
    return (
        ConductReport.objects.filter(status=ConductReport.Status.OPEN)
        .select_related("match", "reporter", "reported")
        .order_by("created_at")
    )


def period_start(period: str, *, today: date | None = None) -> date:
    """The first day of the period a leaderboard covers."""
    today = today or now().date()
    if period == LeaderboardEntry.Period.MONTH:
        return today.replace(day=1)
    # All-time boards still need a stable key; epoch-ish is as good as any.
    return date(1970, 1, 1)


def leaderboard(
    *,
    sport: Sport,
    turf=None,
    metric: str = LeaderboardEntry.Metric.RATING,
    stat_key: str = "",
    period: str = LeaderboardEntry.Period.MONTH,
) -> QuerySet[LeaderboardEntry]:
    """A computed board, read as it was last written (nightly)."""
    return (
        LeaderboardEntry.objects.filter(
            sport=sport,
            turf=turf,
            metric=metric,
            stat_key=stat_key,
            period=period,
            period_start=period_start(period),
        )
        .select_related("profile", "profile__user", "sport")
        .order_by("rank")
    )


def rating_history(*, profile: PlayerProfile, sport: Sport, limit: int = 20) -> list[dict]:
    """The chart on the profile: what the rating was after each match."""
    from .models import RatingChange

    changes = (
        RatingChange.objects.filter(profile=profile, sport=sport)
        .select_related("match", "match__booking__ground__turf")
        .order_by("-played_at")[:limit]
    )
    return [
        {
            "match_id": change.match_id,
            "played_at": change.played_at,
            "turf_name": change.match.booking.ground.turf.name,
            "before": change.before_overall,
            "after": change.after_overall,
            "delta": change.delta,
            "breakdown": change.breakdown,
        }
        for change in reversed(list(changes))
    ]


def _stat_total(row, key: str) -> Decimal:
    return Decimal((row.stat_totals or {}).get(key, "0"))
