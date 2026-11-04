"""Read-side queries for matches and squads (CLAUDE.md).

The match board is the important one: it is the first screen a player without a booking
sees, and it has to be cheap enough to filter interactively.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Avg, Count, F, OuterRef, Prefetch, Q, QuerySet, Subquery
from psycopg.types.range import TimestamptzRange

from apps.bookings.models import ACTIVE_BOOKING_STATUSES
from apps.core.utils import DHAKA, now
from apps.players.models import PlayerSportRating

from .models import (
    JoinRequest,
    Match,
    MatchInvite,
    MatchPlayer,
    MatchStatus,
    MatchVisibility,
    Squad,
    SquadMembership,
)

MAX_BOARD_RADIUS_KM = 50


def _with_related(queryset: QuerySet[Match]) -> QuerySet[Match]:
    return queryset.select_related(
        "booking",
        "booking__ground",
        "booking__ground__turf",
        "booking__booked_by",
        "sport",
        "sport_format",
        "squad",
        "squad__leader",
    ).prefetch_related(
        Prefetch(
            "players",
            # The ratings are prefetched too: the roster row shows each player's rating
            # *in this sport*, and reading it off the profile sent the match page back
            # to the database once per player on the roster.
            queryset=MatchPlayer.objects.select_related(
                "player", "player__player_profile"
            ).prefetch_related("player__player_profile__sport_ratings"),
        ),
    )


def match_queryset() -> QuerySet[Match]:
    return _with_related(Match.objects.all())


#: Mean overall of a match's roster **in that match's sport**, as a subquery.
#:
#: A join would multiply the roster rows and quietly corrupt the `spots_left` count
#: alongside it, so the average is computed per match in the database instead.
_ROSTER_AVERAGE = Subquery(
    PlayerSportRating.objects.filter(
        sport=OuterRef("sport_id"),
        profile__user__match_entries__match=OuterRef("pk"),
    )
    .values("sport")
    .annotate(average=Avg("overall"))
    .values("average")[:1]
)


def _annotated(queryset: QuerySet[Match]) -> QuerySet[Match]:
    """Roster size, spots left and the roster's average rating, all in the database.

    ``spots_left`` has to be a database value for the board's "needs at least N" filter
    to work at all, and the average is what lets a player judge a match before asking to
    join (DOMAIN §6).
    """
    return queryset.annotate(
        roster_size=Count("players", distinct=True),
        spots_left=F("capacity") - Count("players", distinct=True),
        average_overall=_ROSTER_AVERAGE,
    )


def board_matches(
    *,
    user,
    sport: str | None = None,
    area: str | None = None,
    near: tuple[float, float] | None = None,
    radius_km: float | None = None,
    day: date | None = None,
    time_from: time | None = None,
    time_to: time | None = None,
    needed_min: int | None = None,
    rating_min: int | None = None,
    rating_max: int | None = None,
) -> QuerySet[Match]:
    """Open matches a player can ask to join (DOMAIN §6 match board).

    Only ``board`` visibility, only upcoming, only matches whose booking still holds its
    slot — a match whose booking was cancelled must not be advertised. Matches the player
    is already in are excluded: they are not looking for those.
    """
    queryset = _annotated(
        _with_related(
            Match.objects.filter(
                visibility=MatchVisibility.BOARD,
                status=MatchStatus.UPCOMING,
                booking__status__in=ACTIVE_BOOKING_STATUSES,
                booking__time_range__startswith__gt=now(),
            )
        )
    ).filter(spots_left__gt=0)

    if user and user.is_authenticated:
        queryset = queryset.exclude(players__player=user)

    if sport:
        queryset = queryset.filter(sport__slug=sport)
    if area:
        queryset = queryset.filter(booking__ground__turf__area__iexact=area)

    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=DHAKA)
        end = datetime.combine(day + timedelta(days=1), time(6, 0), tzinfo=DHAKA)
        queryset = queryset.filter(booking__time_range__overlap=TimestamptzRange(start, end))

    if time_from is not None or time_to is not None:
        # Filtering on the Dhaka-local hour of day, which is how a player thinks about
        # "evenings only" — not on a UTC timestamp.
        queryset = queryset.extra(
            where=[
                "EXTRACT(HOUR FROM (lower(bookings_booking.time_range) "
                "AT TIME ZONE 'Asia/Dhaka')) BETWEEN %s AND %s"
            ],
            params=[
                time_from.hour if time_from else 0,
                time_to.hour if time_to else 23,
            ],
        )

    if needed_min:
        queryset = queryset.filter(spots_left__gte=needed_min)

    if rating_min is not None or rating_max is not None:
        # An unrated roster must not vanish from a filtered board — a brand-new player's
        # match is exactly what somebody browsing wants to find.
        band = Q(average_overall__isnull=True)
        rated = Q()
        if rating_min is not None:
            rated &= Q(average_overall__gte=rating_min)
        if rating_max is not None:
            rated &= Q(average_overall__lte=rating_max)
        queryset = queryset.filter(band | rated)

    if near:
        point = Point(near[0], near[1], srid=4326)
        queryset = queryset.annotate(distance=Distance("booking__ground__turf__location", point))
        if radius_km:
            queryset = queryset.filter(
                booking__ground__turf__location__distance_lte=(
                    point,
                    D(km=min(radius_km, MAX_BOARD_RADIUS_KM)),
                )
            )
        return queryset.order_by("distance", "booking__time_range")

    return queryset.order_by("booking__time_range")


def average_rating_for(match: Match) -> float | None:
    """Mean overall of the roster, in this match's sport (DOMAIN §6).

    Uses the annotation when the match came from a board query, and falls back to a
    query for a single match page — where one extra query is not worth avoiding.

    The test is `hasattr`, not "is it None": a board row whose roster is entirely
    unrated is annotated with NULL, which is the *answer* (D38 — such a match stays on
    the board), not a missing annotation. Reading it as missing sent the board back to
    the database once per card, so a board of new players cost one query per match —
    exactly the page that matters most, and exactly the players it matters most for.
    """
    if hasattr(match, "average_overall"):
        annotated = match.average_overall
        return round(float(annotated), 1) if annotated is not None else None

    result = PlayerSportRating.objects.filter(
        sport=match.sport_id, profile__user__match_entries__match=match
    ).aggregate(average=Avg("overall"))
    return round(result["average"], 1) if result["average"] is not None else None


def matches_for_player(user) -> QuerySet[Match]:
    """Every match this player is in or organises."""
    return _with_related(
        Match.objects.filter(
            Q(players__player=user) | Q(booking__booked_by=user) | Q(squad__leader=user)
        )
    ).distinct()


def upcoming_for_player(user) -> QuerySet[Match]:
    return (
        matches_for_player(user)
        .filter(status=MatchStatus.UPCOMING, booking__time_range__endswith__gt=now())
        .order_by("booking__time_range")
    )


def visible_matches(user) -> QuerySet[Match]:
    """Everything this user may open: theirs, on the board, their squads', or invited.

    The permission class re-checks per object; this is what keeps the *queryset* from
    leaking a private match's existence through a list endpoint.
    """
    if not user or not user.is_authenticated:
        return Match.objects.none()

    squad_ids = SquadMembership.objects.filter(
        player=user, status=SquadMembership.Status.ACTIVE
    ).values_list("squad_id", flat=True)

    return _with_related(
        Match.objects.filter(
            Q(players__player=user)
            | Q(booking__booked_by=user)
            | Q(squad__leader=user)
            | Q(visibility=MatchVisibility.BOARD)
            | Q(visibility=MatchVisibility.SQUAD, squad_id__in=squad_ids)
            | Q(
                invites__invited_player=user,
                invites__status=MatchInvite.Status.LEADER_APPROVED,
            )
        )
    ).distinct()


def pending_requests_for(match: Match) -> QuerySet[JoinRequest]:
    return match.join_requests.filter(status=JoinRequest.Status.PENDING).select_related(
        "player", "player__player_profile"
    )


def live_invites_for(match: Match) -> QuerySet[MatchInvite]:
    return match.invites.filter(
        status__in=[MatchInvite.Status.PROPOSED, MatchInvite.Status.LEADER_APPROVED]
    ).select_related("invited_player", "invited_by")


def squads_for_player(user) -> QuerySet[Squad]:
    if not user or not user.is_authenticated:
        return Squad.objects.none()
    return (
        Squad.objects.filter(
            memberships__player=user, memberships__status=SquadMembership.Status.ACTIVE
        )
        .select_related("leader")
        .prefetch_related("sports", "memberships__player__player_profile")
        .distinct()
    )


def squad_queryset() -> QuerySet[Squad]:
    return Squad.objects.select_related("leader").prefetch_related(
        "sports",
        Prefetch(
            "memberships",
            queryset=SquadMembership.objects.filter(
                status=SquadMembership.Status.ACTIVE
            ).select_related("player", "player__player_profile"),
        ),
    )


def my_match_invites(user) -> QuerySet[MatchInvite]:
    """Invitations awaiting this player's answer."""
    return MatchInvite.objects.filter(
        invited_player=user, status=MatchInvite.Status.LEADER_APPROVED
    ).select_related("match", "match__booking", "match__booking__ground__turf", "match__sport")


def my_squad_invites(user):
    from .models import SquadInvite

    return SquadInvite.objects.filter(
        player=user, status=SquadInvite.Status.PENDING
    ).select_related("squad", "invited_by")
