"""Read-side queries for turfs (CLAUDE.md).

Public listings must never leak an unapproved venue, so **every** public selector starts
from :func:`public_turfs` rather than ``Turf.objects``.
"""

from __future__ import annotations

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Prefetch, Q, QuerySet

from .models import Ground, Turf, TurfMembership

#: Dhaka. Used only to sanity-check that a "near me" point is on the planet.
MAX_SEARCH_RADIUS_KM = 50


def _with_related(queryset: QuerySet[Turf], *, only_active_grounds: bool) -> QuerySet[Turf]:
    """Prefetch everything a turf serializer touches.

    ``only_active_grounds`` is the one thing that differs between audiences, and it
    matters: a player must not see a ground that is not bookable, while an **owner has
    to** — a ground is created inactive, so hiding it would hide the very row they need
    in order to price and activate it. Reviewing admins need the same full picture.
    """
    grounds = Ground.objects.all()
    if only_active_grounds:
        grounds = grounds.filter(is_active=True)

    return queryset.prefetch_related(
        "amenities",
        "photos",
        Prefetch(
            "grounds",
            queryset=grounds.prefetch_related("sport_formats__sport", "price_rules"),
        ),
        "operating_hours",
    )


def public_turfs() -> QuerySet[Turf]:
    """Approved turfs only — the single gate for everything a player can see."""
    return _with_related(Turf.objects.filter(status=Turf.Status.APPROVED), only_active_grounds=True)


def turfs_for_staff(user) -> QuerySet[Turf]:
    """Every turf this user works at, whatever its status, with every ground."""
    if not user or not user.is_authenticated:
        return Turf.objects.none()
    return _with_related(
        Turf.objects.filter(
            memberships__user=user, memberships__status=TurfMembership.Status.ACTIVE
        ).distinct(),
        only_active_grounds=False,
    )


def review_queue() -> QuerySet[Turf]:
    """What an admin has to look at, oldest submission first."""
    return _with_related(
        Turf.objects.filter(status=Turf.Status.PENDING_REVIEW), only_active_grounds=False
    ).order_by("submitted_at")


def all_turfs_for_review() -> QuerySet[Turf]:
    """Every turf, in any status, for an admin. Inactive grounds included."""
    return _with_related(Turf.objects.all(), only_active_grounds=False)


def search_turfs(
    *,
    queryset: QuerySet[Turf] | None = None,
    near: tuple[float, float] | None = None,
    radius_km: float | None = None,
    sport: str | None = None,
    area: str | None = None,
    query: str | None = None,
) -> QuerySet[Turf]:
    """Filter and order the public listing.

    ``near`` is ``(longitude, latitude)`` — PostGIS order, not the ``lat,lng`` humans
    write, which is why the view parses the query parameter and this takes a tuple.
    With a point, results are annotated with ``distance`` and sorted nearest-first;
    without one they fall back to alphabetical, so the endpoint is still useful to a
    player who declines geolocation.
    """
    turfs = public_turfs() if queryset is None else queryset

    if sport:
        turfs = turfs.filter(
            grounds__is_active=True, grounds__sport_formats__sport__slug=sport
        ).distinct()
    if area:
        turfs = turfs.filter(area__iexact=area)
    if query:
        turfs = turfs.filter(
            Q(name__icontains=query) | Q(area__icontains=query) | Q(address__icontains=query)
        )

    if near:
        point = Point(near[0], near[1], srid=4326)
        turfs = turfs.annotate(distance=Distance("location", point))
        if radius_km:
            turfs = turfs.filter(
                location__distance_lte=(point, D(km=min(radius_km, MAX_SEARCH_RADIUS_KM)))
            )
        return turfs.order_by("distance")

    return turfs.order_by("name")


def bookable_grounds(turf: Turf) -> QuerySet[Ground]:
    return turf.grounds.filter(is_active=True).prefetch_related("sport_formats__sport")
